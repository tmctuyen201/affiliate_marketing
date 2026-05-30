"""
TikTok Affiliate - Permanent Login (Camoufox + SadCaptcha)
============================================================
Bypasses TikTok bot detection using C++ level fingerprint spoofing.

Status: TESTED AND WORKING
- Camoufox bypasses TikTok detection (no captcha!)
- Country selector (VN +84) working
- SadCaptcha ready for any captcha that appears
- Session persistence for 2-4 week reuse

Requirements:
    pip install camoufox[geoip] tiktok-captcha-solver
    camoufox fetch

Usage:
    python login_camoufox.py --password YOUR_PASS --sadcaptcha-key YOUR_KEY
    python login_camoufox.py --resume
    python login_camoufox.py --resume --extract
"""

import asyncio
import json
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles"
SESSION_FILE = PROFILES_DIR / "session_state.json"
PRODUCTS_FILE = BASE_DIR / "affiliate_products.json"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"

SELLER_URL = "https://seller-vn.tiktok.com"
LOGIN_URL = f"{SELLER_URL}/account/login"
AFFILIATE_URL = f"{SELLER_URL}/affiliate"
AFFILIATE_PRODUCT_URL = f"{SELLER_URL}/affiliate/product"

PHONE = "0902018245"


async def dismiss_banner(page):
    await page.evaluate(
        '() => { const b = document.querySelector("tiktok-cookie-banner"); if(b) b.remove(); }'
    )


async def select_vietnam(page):
    """Open country dropdown and select Vietnam +84."""
    # Click country selector
    await page.mouse.click(830, 239)
    await asyncio.sleep(3)

    # Scroll to Vietnam
    await page.evaluate("""() => {
        for (const el of document.querySelectorAll('span')) {
            if (el.innerText.trim() === 'Vietnam +84') {
                el.scrollIntoView({block: 'center'});
                return;
            }
        }
    }""")
    await asyncio.sleep(2)

    # Click at position after scroll
    pos = await page.evaluate("""() => {
        for (const el of document.querySelectorAll('span')) {
            if (el.innerText.trim() === 'Vietnam +84') {
                const r = el.getBoundingClientRect();
                return {x: r.x + r.width/2, y: r.y + r.height/2};
            }
        }
        return null;
    }""")

    if pos:
        await page.mouse.click(pos["x"], pos["y"])
        await asyncio.sleep(2)
        return True
    return False


async def login_flow(page, phone, password, solver=None):
    """Full login flow with Camoufox."""
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    print("[1] Opening TikTok login...")
    await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
    await asyncio.sleep(8)
    await dismiss_banner(page)

    print("[2] TikTok account login...")
    btn = page.locator('span:has-text("Đăng nhập bằng tài khoản TikTok")')
    if await btn.count() > 0:
        await btn.first.click(force=True)
        await asyncio.sleep(8)
        await dismiss_banner(page)

    print("[3] Phone/email login...")
    phone_opt = page.locator('text=Sử dụng số điện thoại/email/tên người dùng')
    if await phone_opt.count() > 0:
        await phone_opt.first.click(force=True)
        await asyncio.sleep(3)

    print("[4] Vietnam +84...")
    await select_vietnam(page)

    country = await page.evaluate(
        '() => { const el = document.querySelector(\'[class*="AreaLabel"]\'); return el ? el.innerText.trim() : "?"; }'
    )
    print(f"  Country: {country}")

    print(f"[5] Phone: {phone}")
    await page.locator('input[name="mobile"]').first.click(force=True)
    await page.keyboard.type(phone, delay=80)

    print("[6] Password mode...")
    pwd_link = page.locator('text=Đăng nhập bằng mật khẩu')
    if await pwd_link.count() > 0:
        await pwd_link.first.click(force=True)
        await asyncio.sleep(2)

    print("[7] Password...")
    await page.locator('input[type="password"]').first.click(force=True)
    await page.keyboard.type(password, delay=80)
    await asyncio.sleep(1)

    await page.screenshot(path=str(SCREENSHOTS_DIR / "before_login.png"))

    print("[8] Clicking login...")
    for btn in await page.locator('button:has-text("Đăng nhập")').all():
        try:
            if await btn.is_visible():
                await btn.click(force=True)
                break
        except:
            continue

    await asyncio.sleep(5)

    # Handle captcha
    if solver and await solver.captcha_is_present():
        print("[!] Captcha detected! Solving...")
        try:
            await solver.solve_captcha_if_present()
            print("[+] Captcha solved!")
        except Exception as e:
            print(f"[-] SadCaptcha error: {e}")
            try:
                await solver.solve_puzzle()
                print("[+] Puzzle solved!")
            except Exception as e2:
                print(f"[-] Puzzle error: {e2}")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "captcha_failed.png"))
                return False
    else:
        print("[9] No captcha!")

    await asyncio.sleep(8)
    await page.screenshot(path=str(SCREENSHOTS_DIR / "after_login.png"))

    url = page.url
    body = await page.inner_text("body")

    if "seller-vn" in url and "login" not in url:
        print("[+] LOGIN SUCCESS!")
        return True

    if "đã xảy ra lỗi" in body.lower() or "đã đạt" in body.lower():
        print("[-] Rate limited or temporary error")
        return False

    if "không chính xác" in body.lower():
        print("[-] Wrong password or country code")
        return False

    print(f"[?] Unknown: {url}")
    return False


async def extract_affiliate_links(page):
    """Extract product links from affiliate dashboard."""
    print("\n[*] Extracting affiliate links...")
    await page.goto(AFFILIATE_PRODUCT_URL, timeout=30000, wait_until="domcontentloaded")
    await asyncio.sleep(5)

    products = await page.evaluate("""() => {
        const scripts = document.querySelectorAll('script');
        for (const s of scripts) {
            const text = s.textContent || '';
            if (text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                try {
                    const json = JSON.parse(text);
                    const data = json['__UNIVERSAL_DATA_FOR_REHYDRATION__'];
                    const products = [];
                    const find = (obj) => {
                        if (!obj || typeof obj !== 'object') return;
                        if (obj.product_id || obj.productId) {
                            products.push({
                                id: obj.product_id || obj.productId,
                                title: obj.title || obj.product_name || '',
                                price: obj.price || '',
                                url: obj.seo_url || obj.url || '',
                                commission: obj.commission_rate || ''
                            });
                        }
                        for (const k of Object.keys(obj)) find(obj[k]);
                    };
                    find(data);
                    return products;
                } catch(e) { return []; }
            }
        }
        return [];
    }""")

    if products:
        print(f"[+] Found {len(products)} products")
    else:
        print("[i] No products found from rehydration")

    return products


async def save_session(context):
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    state = await context.storage_state()
    with open(SESSION_FILE, "w") as f:
        json.dump(state, f, indent=2)
    cookies = await context.cookies()
    print(f"[+] Session saved ({len(cookies)} cookies)")


async def load_session(context):
    if SESSION_FILE.exists():
        with open(SESSION_FILE) as f:
            state = json.load(f)
        await context.add_cookies(state.get("cookies", []))
        age = (datetime.now() - datetime.fromtimestamp(SESSION_FILE.stat().st_mtime)).days
        print(f"[+] Session loaded (age: {age} days)")
        return age < 14
    return False


async def check_session(page):
    try:
        await page.goto(AFFILIATE_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        return "login" not in page.url.lower()
    except:
        return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", default=PHONE)
    parser.add_argument("--password")
    parser.add_argument("--sadcaptcha-key")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--extract", action="store_true")
    args = parser.parse_args()

    print("=" * 50)
    print("TikTok Affiliate - Camoufox Login")
    print(f"SadCaptcha: {'Enabled' if args.sadcaptcha_key else 'Disabled'}")
    print(f"Mode: {'Resume' if args.resume else 'Fresh login'}")
    print("=" * 50)

    from camoufox.async_api import AsyncCamoufox
    from camoufox.addons import DefaultAddons

    async with AsyncCamoufox(
        headless=True, geoip=True, humanize=True,
        exclude_addons=[DefaultAddons.UBO]
    ) as browser:
        context = await browser.new_context()

        # Try resume
        if args.resume and await load_session(context):
            page = await context.new_page()
            if await check_session(page):
                print("[+] Session valid!")
                if args.extract:
                    products = await extract_affiliate_links(page)
                    with open(PRODUCTS_FILE, "w") as f:
                        json.dump(products, f, indent=2, ensure_ascii=False)
                await save_session(context)
                return
            print("[!] Session expired")

        if not args.password:
            print("[!] --password required for fresh login")
            return

        page = await context.new_page()
        solver = None
        if args.sadcaptcha_key:
            from tiktok_captcha_solver import AsyncPlaywrightSolver
            solver = AsyncPlaywrightSolver(page=page, sadcaptcha_api_key=args.sadcaptcha_key)
            print("[+] SadCaptcha ready")

        success = await login_flow(page, args.phone, args.password, solver)

        if success:
            await save_session(context)
            if args.extract:
                products = await extract_affiliate_links(page)
                with open(PRODUCTS_FILE, "w") as f:
                    json.dump(products, f, indent=2, ensure_ascii=False)
                print(f"[+] {len(products)} products saved")
            print("\n" + "=" * 50)
            print("SUCCESS! Session saved.")
            print("Next: python login_camoufox.py --resume")
            print("=" * 50)
        else:
            print("\n[-] Login failed")


if __name__ == "__main__":
    asyncio.run(main())
