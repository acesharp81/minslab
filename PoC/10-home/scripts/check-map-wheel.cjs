/* Wheel zoom and camera changes keep one MapLibre canvas alive. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const root=process.env.HOME_CHECK_URL||'http://127.0.0.1:18100/poc/home/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.HOME_CHECK_CHROME||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(root);await page.locator('#housing-map-3d canvas').waitFor({state:'visible',timeout:60000});
  await page.locator('.map-scene-block').first().waitFor({state:'visible',timeout:60000});
  const canvas=await page.locator('#housing-map-3d canvas').elementHandle();
  const zoom=()=>page.evaluate(()=>MapThreeD.zoom());
  const waitChanged=async(before,inward)=>{for(let i=0;i<60;i++){const value=await zoom();if(inward?value>before+.15:value<before-.15)return value;await page.waitForTimeout(100);}assert.fail('wheel did not change 3D zoom');};
  const box=await page.locator('#housing-map-3d').boundingBox();
  await page.mouse.move(box.x+box.width*.65,box.y+box.height*.6);
  let before=await zoom();await page.mouse.wheel(0,-260);await waitChanged(before,true);
  assert.equal(await canvas.evaluate(node=>node.isConnected),true);
  for(let i=0;i<10;i++)await page.mouse.wheel(0,450);
  for(let i=0;i<60;i++){if(await zoom()<12)break;await page.waitForTimeout(100);}
  assert((await zoom())<12,'zoom out reaches municipality level');
  assert.equal(await canvas.evaluate(node=>node.isConnected),true);
  await page.locator('.map-scene-municipality').first().waitFor({state:'visible'});
  await page.mouse.move(box.x+box.width*.65,box.y+box.height*.6);
  for(let i=0;i<8;i++)await page.mouse.wheel(0,-450);
  for(let i=0;i<60;i++){if(await zoom()>=13)break;await page.waitForTimeout(100);}
  await page.locator('.map-scene-block').first().waitFor({state:'visible',timeout:30000});
  assert.equal(await canvas.evaluate(node=>node.isConnected),true);
  assert((await zoom())>=13);
  const panel=page.locator('.map-side-panel');
  assert(await panel.evaluate(node=>node.scrollHeight>node.clientHeight));
  await panel.evaluate(node=>{node.scrollTop=0;});before=await zoom();
  await panel.hover();await page.mouse.wheel(0,500);
  for(let i=0;i<30;i++){if(await panel.evaluate(node=>node.scrollTop>0))break;await page.waitForTimeout(100);}
  assert((await panel.evaluate(node=>node.scrollTop))>0,'supply panel scrolls independently');
  assert.equal(await zoom(),before);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',continuousCanvas:true,zoomOutAndBack:true,panelScroll:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
