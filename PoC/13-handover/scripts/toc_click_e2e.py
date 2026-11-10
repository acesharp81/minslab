"""Title, arrow, keyboard and mobile expansion regression. No model calls."""
import argparse,json
from pathlib import Path
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
a=argparse.ArgumentParser();a.add_argument('--patched',action='store_true');args=a.parse_args()
out=ROOT/'test-results/toc-title'/('patched' if args.patched else 'live');out.mkdir(parents=True,exist_ok=True)
errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1600,'height':1000},reduced_motion='reduce');page.on('pageerror',lambda e:errors.append(str(e)))
 if args.patched:page.route('**/assets/reader.js',lambda route:route.fulfill(path=str(ROOT/'app/web/reader.js'),content_type='text/javascript'))
 page.goto('https://www.minslab.kr/handover/#8160f1f002f24fff8d22b5ade2776c0c')
 if page.locator('#accessToken').is_visible():page.locator('#accessToken').fill(dotenv_values(ROOT/'.env')['HANDOVER_ACCESS_TOKEN']);page.get_by_role('button',name='접속하기',exact=True).click()
 title=page.locator('#reportToc a').filter(has_text='우선순위와 실행 순서');title.wait_for();branch=title.locator('xpath=../..');children=branch.locator(':scope > .toc-children')
 assert branch.get_attribute('open') is None
 title.click();expect(children).to_be_visible();expect(page.frame_locator('#reportFrame').locator('#priorities')).to_be_in_viewport()
 title.click();expect(children).not_to_be_visible()
 branch.locator(':scope > summary > .toc-arrow').click();expect(children).to_be_visible();branch.locator(':scope > summary > .toc-arrow').click();expect(children).not_to_be_visible()
 title.focus();page.keyboard.press('Enter');expect(children).to_be_visible();page.keyboard.press('Enter');expect(children).not_to_be_visible()
 for width,height in [(1100,800),(390,844)]:
  page.set_viewport_size({'width':width,'height':height});page.locator('.reader-panel-toggle[data-reader-panel="toc"]').click();title.click();expect(children).to_be_visible();expect(page.locator('.reader-toc')).to_be_visible()
  page.screenshot(path=str(out/f'expanded-{width}.png'))
  child=children.locator('a').first;target=child.get_attribute('href');child.click();expect(page.locator('.reader-toc')).not_to_be_visible();expect(page.frame_locator('#reportFrame').locator(target)).to_be_in_viewport()
  page.locator('.reader-panel-toggle[data-reader-panel="toc"]').click();title.click();expect(children).not_to_be_visible();page.locator('.reader-panel-close[data-reader-panel="toc"]').click()
 assert not errors;b.close()
result={'title_expands_and_collapses':True,'arrow_expands_and_collapses':True,'enter_key_toggles':True,'tablet_and_phone_keep_tree_open_on_parent':True,'leaf_navigates_and_closes_overlay':True,'javascript_errors':errors,'model_calls':0}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
