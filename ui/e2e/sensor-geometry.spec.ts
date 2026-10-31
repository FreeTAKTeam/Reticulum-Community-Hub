import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(readFileSync(new URL("./fixtures/r3s-native.json", import.meta.url), "utf8"));
const style = { version:8, glyphs:"https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf", sources:{},layers:[{id:"background",type:"background",paint:{"background-color":"#202a30"}}] };
test("RCH renders native sensors and removes unavailable coverage",async ({page},info)=>{
  let phase = "fresh";
  await page.route("http://127.0.0.1:18088/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==="/Sensors") return phase==="failed" ? route.fulfill({status:503,json:{error:"Sensor service unavailable"}}) : route.fulfill({json:fixture[phase]});
    return route.fulfill({json:path==="/Status"?{status:"ok"}:[]});
  });
  await page.addInitScript(()=>{
    localStorage.setItem("rth-ui-connection",JSON.stringify({baseUrl:"http://127.0.0.1:18088",authMode:"apiKey",apiKey:"disposable-fixture",rememberSecrets:true}));
    localStorage.setItem("rth-ui-map-settings",JSON.stringify({showMarkerLabels:true,mapView:{lat:45,lon:-63,zoom:13}}));
  });
  await page.goto("/webmap");
  const panel=page.getByTestId("sensor-geometry-panel");
  await panel.locator("summary").click();
  await expect(panel.getByText("Drone B",{exact:true})).toBeVisible();
  await expect(panel.locator("article")).toHaveCount(5);
  const features=()=>panel.evaluate((el:any)=> (el.__vueParentComponent.props.map.getStyle().sources["r3s-sensor-geometry"] as any)?.data?.features ?? []);
  await panel.evaluate((el:any,nextStyle)=>el.__vueParentComponent.props.map.setStyle(nextStyle),style);
  await expect.poll(async()=> (await features()).filter((f:any)=>f.geometry.type==="MultiPolygon").length).toBe(5);
  await expect(page.locator(".maplibregl-canvas")).toHaveCount(1);
  await panel.locator("section").last().getByRole("checkbox").first().uncheck();
  await expect.poll(async()=> (await features()).filter((f:any)=>f.geometry.type==="MultiPolygon").length).toBe(1);
  await panel.locator("section").last().getByRole("checkbox").first().check();
  await panel.getByRole("button",{name:"Locate"}).last().click();
  await page.waitForTimeout(500);
  await page.screenshot({path:info.outputPath("rch-r3s-map.png")});
  phase="stale";
  await expect(panel.getByText(/Stale ·/)).toHaveCount(5);
  await expect.poll(async()=> (await features()).filter((f:any)=>f.geometry.type==="MultiPolygon").length).toBe(0);
  phase="failed";
  await expect(panel.getByRole("alert")).toBeVisible();
  await expect(panel.locator("article")).toHaveCount(0);
  await expect.poll(async()=> (await features()).length).toBe(0);
});
