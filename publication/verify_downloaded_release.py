"""Published release download and installed HTTP inference smoke check.

This verifies packaging/integrity only; it does not score forecasts or run research.
"""
import hashlib,json,os,subprocess,sys,time,urllib.request,urllib.error,zipfile
from pathlib import Path
import numpy as np
from retail_forecasting.deployment.bundle import load_runtime_engine

ROOT=Path(__file__).resolve().parents[1]
BASE="https://github.com/tanjilaislam414659/retail-forecasting-inventory/releases/download/v0.1.0"
OUT=ROOT/"artifacts"; DOWNLOADS=OUT/"downloads"; DOWNLOADS.mkdir(parents=True,exist_ok=True)
NAMES=("SHA256SUMS.txt","retail-forecasting-runtime-v0.1.0.zip","LICENSE","DATA-LICENSE.md","CC-BY-4.0-NOTICE.txt")
records=[]
api="https://api.github.com/repos/tanjilaislam414659/retail-forecasting-inventory"
token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
release_metadata=None
for name in NAMES:
    canonical_error=None
    try:
        req=urllib.request.Request(BASE+"/"+name,headers={"User-Agent":"Retail-Forecasting-Release-Check"})
        with urllib.request.urlopen(req,timeout=10) as response:
            raw=response.read();status=response.status
        route="anonymous browser-download URL"
    except (urllib.error.URLError,TimeoutError) as error:
        canonical_error=type(error).__name__+": "+str(error)
        if not token:raise RuntimeError("Browser download unavailable; authenticated API fallback needs GH_TOKEN or GITHUB_TOKEN") from error
        print("::warning::Browser download unavailable for "+name+"; using official authenticated asset API. Anonymous access is not verified.",flush=True)
        headers={"User-Agent":"Retail-Forecasting-Release-Check","Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"}
        if release_metadata is None:
            with urllib.request.urlopen(urllib.request.Request(api+"/releases/tags/v0.1.0",headers=headers),timeout=25) as response:release_metadata=json.load(response)
        asset=next(item for item in release_metadata["assets"] if item["name"]==name)
        headers["Accept"]="application/octet-stream"
        with urllib.request.urlopen(urllib.request.Request(api+"/releases/assets/"+str(asset["id"]),headers=headers),timeout=25) as response:
            raw=response.read();status=response.status
        route="authenticated official release-asset API fallback"
    assert status==200
    (DOWNLOADS/name).write_bytes(raw)
    records.append({"name":name,"url":BASE+"/"+name,"http_status":status,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"route":route,"canonical_error":canonical_error})
checks=dict(line.split(None,1)[::-1] for line in (DOWNLOADS/"SHA256SUMS.txt").read_text().splitlines())
for item in records:
    if item["name"]!="SHA256SUMS.txt":assert item["sha256"]==checks[item["name"]]
expected=json.loads((ROOT/"publication/runtime-attachment.json").read_bytes())
archive=DOWNLOADS/"retail-forecasting-runtime-v0.1.0.zip"
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected["sha256"]
assert (DOWNLOADS/"LICENSE").read_bytes()==(ROOT/"LICENSE").read_bytes()
destination=OUT/"runtime";destination.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as z:
    for name in z.namelist():assert (destination/name).resolve().is_relative_to(destination.resolve())
    z.extractall(destination)
bundle=destination/"milestone-9-v0.1.0";engine=load_runtime_engine(bundle)
url="http://127.0.0.1:8765"
def request(path,payload=None):
    body=None if payload is None else json.dumps(payload).encode()
    try:response=urllib.request.urlopen(urllib.request.Request(url+path,data=body,headers={"Content-Type":"application/json"}),timeout=5)
    except urllib.error.HTTPError as e:response=e
    with response:return response.status,response.read()
with (OUT/"release-smoke.log").open("w",encoding="utf-8") as log:
    process=subprocess.Popen([sys.executable,"-m","retail_forecasting.demo","--root",str(bundle),"--runtime-bundle","--port","8765"],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    try:
        deadline=time.monotonic()+30
        while True:
            try:
                if request("/health")[0]==200:break
            except (urllib.error.URLError,TimeoutError):pass
            if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError("Service did not start")
            time.sleep(.1)
        for path in ("/","/health","/ready","/metadata","/docs","/demo/api/evaluation","/demo/api/inventory"):
            assert request(path)[0]==200,path
        metadata=json.loads(request("/metadata")[1]);assert len(metadata["supported_skus"])==100 and len(metadata["supported_origins"])==20
        cases=0;maximum_difference=0.
        for sku in ("21212","21166","21533"):
            for origin in (engine.origins[0],engine.origins[-1]):
                status,raw=request("/forecast",{"sku":sku,"origin":origin.isoformat(),"horizon_days":28});assert status==200
                got=json.loads(raw);wanted=engine.predict(sku,origin).model_dump(mode="json");assert len(got["predictions"])==28
                assert "customer" not in raw.decode().lower() and "actual" not in raw.decode().lower()
                for a,b in zip(got["predictions"],wanted["predictions"]):
                    assert a["target_date"]==b["target_date"] and a["horizon_day"]==b["horizon_day"]
                    x=[a["predicted_sales"]]+[a[f"interval_{v}"][e] for v in (80,95) for e in ("lower","upper")]
                    y=[b["predicted_sales"]]+[b[f"interval_{v}"][e] for v in (80,95) for e in ("lower","upper")]
                    np.testing.assert_allclose(x,y,rtol=1e-12,atol=1e-9)
                    maximum_difference=max(maximum_difference,float(np.max(np.abs(np.array(x)-y))))
                cases+=1
        assert request("/forecast",{"sku":"unknown","origin":"2011-11-07"})[0]==422
    finally:
        process.terminate();process.wait(timeout=15)
result={"status":"PASS","scope":"Published attachment integrity and installed inference regression; no experiment or scoring","anonymous_downloads_verified":all(item["canonical_error"] is None for item in records),"download_checks":records,"runtime_zip_sha256":expected["sha256"],"parity_cases":cases,"dated_predictions":cases*28,"numeric_values":cases*28*5,"maximum_absolute_difference":maximum_difference,"rtol":1e-12,"atol":1e-9,"server_stopped":True,"commit":os.environ.get("GITHUB_SHA")}
(OUT/"release-verification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2))
