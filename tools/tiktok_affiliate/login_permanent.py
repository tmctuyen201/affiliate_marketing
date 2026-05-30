"""
TikTok Affiliate - Permanent Login Solution
=============================================
Uses Camoufox (anti-detect browser) + SadCaptcha (captcha solver)
to bypass TikTok's bot detection permanently.

Architecture:
    Camoufox (C++ fingerprint spoofing) -> Undetectable by TikTok
    SadCaptcha (auto captcha solving) -> Handles all 4 TikTok captcha types
    Session persistence (storage_state) -> Cookies last 2-4 weeks

Requirements:
    pip install camoufox tiktok-captcha-solver playwright-stealth

Usage:
    python login_permanent.py                          # Fresh login
    python login_permanent.py --resume                 # Use saved session
    python login_permanent.py --extract                # Login + extract links
    python login_permanent.py --sadcaptcha-key YOUR_KEY
"""

import asyncio
import json
import argparse
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles"
SESSION_FILE = PROFILES_DIR / "session_state.json"
COOKIES_FILE = PROFILES_DIR / "cookies.json"
PRODUCTS_FILE = BASE_DIR / "affiliate_products.json"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"

# TikTok URLs
SELLER_URL = "https://seller-vn.tiktok.com"
LOGIN_URL = f"{SELLER_URL}/account/login"
AFFILIATE_URL = f"{SELLER_URL}/affiliate"
AFFILIATE_PRODUCT_URL = f"{SELLER_URL}/affiliate/product"

# Account
PHONE = "0902018245"


async def check_session_valid(page):
    """Check if saved session is still valid."""
    try:
        await page.goto(AFFILIATE_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        if "login" in page.url.lower():
            return False

        body = await page.inner_text("body")
        if any(w in body.lower() for w in ["dashboard", "affiliate", "product", "commission"]):
            return True

        return False
    except Exception as e:
        print(f"[!] Session check error: {e}")
        return False


async def select_vietnam_country(page):
    """Open country dropdown and select Vietnam +84."""
    country_el = await page.evaluate("""
        () => {
            const el = document.querySelector('[class*="AreaSelection"]');
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
        }
    """)

    if not country_el:
        print("[!] Country selector not found")
        return False

    await page.mouse.click(country_el['x'], country_el['y'])
    await asyncio.sleep(2)

    clicked = await page.evaluate("""
        () => {
            const allEls = document.querySelectorAll('span');
            for (const el of allEls) {
                if (el.innerText.trim() === 'Vietnam +84') {
                    el.scrollIntoView({block: 'center'});
                    setTimeout(() => el.click(), 300);
                    return true;
                }
            }
            return false;
        }
    """)

    await asyncio.sleep(2)
    return clicked


async def dismiss_cookie_banner(page):
    """Remove TikTok cookie consent banner."""
    await page.evaluate("""
        () => {
            const b = document.querySelector('tiktok-cookie-banner');
            if (b) b.remove();
        }
    """)


async def login_flow(page, phone, password, solver=None):
    """Execute the full login flow with captcha handling."""
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    print("[1] Opening TikTok Seller login...")
    await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
    await asyncio.sleep(8)
    await dismiss_cookie_banner(page)

    print("[2] Clicking Login with TikTok account...")
    await page.locator("span:has-text('Dang nhap bang tai khoan TikTok')").first.click(force=True)
    await asyncio.sleep(8)
    await dismiss_cookie_banner(page)

    print("[3] Switching to phone login...")
    await page.locator("text=Su dung so dien thoai/email/ten nguoi dung").first.click(force=True)
    await asyncio.sleep(3)

    print("[4] Selecting Vietnam +84...")
    await select_vietnam_country(page)

    print(f"[5] Filling phone: {phone}")
    phone_input = page.locator("input[name='mobile']")
    await phone_input.first.click(force=True)
    await page.keyboard.type(phone, delay=80)
    await asyncio.sleep(0.5)

    print("[6] Switching to password mode...")
    pwd_link = page.locator("text=Dang nhap bang mat khau")
    if await pwd_link.count() > 0:
        await pwd_link.first.click(force=True)
        await asyncio.sleep(2)

    print("[7] Filling password...")
    pwd_input = page.locator("input[type='password']")
    await pwd_input.first.click(force=True)
    await page.keyboard.type(password, delay=80)
    await asyncio.sleep(1)

    await page.screenshot(path=str(SCREENSHOTS_DIR / "before_login.png"))

    print("[8] Clicking login...")
    login_btn = page.locator("button:has-text('Dang nhap')")
    for btn in await login_btn.all():
        try:
            if await btn.is_visible():
                await btn.click(force=True)
                break
        except:
            continue

    await asyncio.sleep(5)

    # Handle captcha
    captcha = page.locator('.captcha-verify-container')
    if await captcha.count() > 0:
        print("[!] CAPTCHA detected!")

        if solver:
            print("[*] SadCaptcha solving automatically...")
            solver.page = page
            try:
                await solver.solve_captcha()
                print("[+] Captcha solved!")
            except Exception as e:
                print(f"[-] SadCaptcha failed: {e}")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "captcha_failed.png"))
                return False
        else:
            print("[!] No solver available")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "captcha_manual.png"))
            return False

    await asyncio.sleep(8)
    await page.screenshot(path=str(SCREENSHOTS_DIR / "after_login.png"))

    body = await page.inner_text("body")

    if "seller-vn.tiktok.com" in page.url and "login" not in page.url:
        print("[+] LOGIN SUCCESSFUL!")
        return True

    if "dat" in body.lower() and "toi da" in body.lower():
        print("[!] Rate limited")
        return False

    print(f"[?] Unknown state: {page.url}")
    return False


async def extract_affiliate_links(page):
    """Extract product affiliate links from dashboard."""
    print("\n[*] Extracting affiliate links...")
    await page.goto(AFFILIATE_PRODUCT_URL, timeout=30000, wait_until="domcontentloaded")
    await asyncio.sleep(5)

    products = await page.evaluate("""
        () => {
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const text = s.textContent || '';
                if (text.includes('__UNIVERSAL_DATA_FOR_REHYDRATION__')) {
                    try {
                        const json = JSON.parse(text);
                        const data = json['__UNIVERSAL_DATA_FOR_REHYDRATION__'];
                        const products = [];
                        const findProducts = (obj) => {
                            if (!obj || typeof obj !== 'object') return;
                            if (obj.product_id || obj.productId) {
                                products.push({
                                    id: obj.product_id || obj.productId,
                                    title: obj.title || obj.product_name || '',
                                    price: obj.price || '',
                                    url: obj.seo_url || obj.url || '',
                                    image: obj.cover_url || obj.image || '',
                                    commission: obj.commission_rate || ''
                                });
                            }
                            for (const key of Object.keys(obj)) {
                                findProducts(obj[key]);
                            }
                        };
                        findProducts(data);
                        return products;
                    } catch(e) { return []; }
                }
            }
            return [];
        }
    """)

    if products:
        print(f"[+] Found {len(products)} products from rehydration data")
        return products

    products = await page.evaluate("""
        () => {
            const items = document.querySelectorAll('[class*="product"], [class*="card"]');
            return Array.from(items).map(el => ({
                title: el.innerText.trim().substring(0, 100),
                links: Array.from(el.querySelectorAll('a[href]')).map(a => a.href)
            })).filter(p => p.links.length > 0);
        }
    """)

    print(f"[i] Found {len(products)} products from DOM")
    return products


async def save_session(context):
    """Save session state for reuse."""
    PROFILES_DIR.mkdir(exist_ok=True)

    state = await context.storage_state()
    with open(SESSION_FILE, "w") as f:
        json.dump(state, f, indent=2)

    cookies = await context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)

    print(f"[+] Session saved to {SESSION_FILE}")
    print(f"    Cookies: {len(cookies)} saved")
    print(f"    Last updated: {datetime.now().isoformat()}")


async def load_session(context):
    """Load saved session state."""
    if SESSION_FILE.exists():
        with open(SESSION_FILE) as f:
            state = json.load(f)
        await context.add_cookies(state.get("cookies", []))
        print(f"[+] Loaded session from {SESSION_FILE}")

        mtime = datetime.fromtimestamp(SESSION_FILE.stat().st_mtime)
        age_days = (datetime.now() - mtime).days
        print(f"    Session age: {age_days} days")

        if age_days > 14:
            print("[!] Session >14 days old - may need refresh")

        return True
    return False


async def main():
    parser = argparse.ArgumentParser(description="TikTok Affiliate - Permanent Login")
    parser.add_argument("--phone", type=str, default=PHONE)
    parser.add_argument("--password", type=str, help="Account password")
    parser.add_argument("--sadcaptcha-key", type=str, help="SadCaptcha API key")
    parser.add_argument("--resume", action="store_true", help="Use saved session")
    parser.add_argument("--extract", action="store_true", help="Extract affiliate links")
    args = parser.parse_args()

    print("=" * 60)
    print("TikTok Affiliate - Permanent Login Solution")
    print("=" * 60)
    print(f"Camoufox: Anti-detect browser (C++ fingerprint spoofing)")
    print(f"SadCaptcha: {'Enabled' if args.sadcaptcha_key else 'Disabled (no key)'}")
    print(f"Mode: {'Resume session' if args.resume else 'Fresh login'}")
    print()

    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        print("[!] Camoufox not installed. Run:")
        print("    pip install camoufox[geoip]")
        print("    camoufox fetch")
        return

    async with AsyncCamoufox(headless=True, geoip=True, humanize=True) as browser:
        context = await browser.new_context()

        if args.resume:
            session_loaded = await load_session(context)
            if session_loaded:
                page = await context.new_page()
                valid = await check_session_valid(page)
                if valid:
                    print("[+] Session is valid!")
                    if args.extract:
                        products = await extract_affiliate_links(page)
                        with open(PRODUCTS_FILE, "w") as f:
                            json.dump(products, f, indent=2, ensure_ascii=False)
                        print(f"[+] Saved to {PRODUCTS_FILE}")
                    await save_session(context)
                    return
                else:
                    print("[!] Session expired - need fresh login")

        if not args.password:
            print("[!] Password required for fresh login")
            print("    Use: --password YOUR_PASSWORD")
            return

        page = await context.new_page()

        solver = None
        if args.sadcaptcha_key:
            try:
                from tiktok_captcha_solver import AsyncPlaywrightSolver
                solver = AsyncPlaywrightSolver(page=page, api_key=args.sadcaptcha_key)
                print("[+] SadCaptcha ready")
            except ImportError:
                print("[!] tiktok_captcha_solver not installed")

        success = await login_flow(page, args.phone, args.password, solver)

        if success:
            await save_session(context)

            if args.extract:
                products = await extract_affiliate_links(page)
                with open(PRODUCTS_FILE, "w") as f:
                    json.dump(products, f, indent=2, ensure_ascii=False)
                print(f"[+] Saved {len(products)} products to {PRODUCTS_FILE}")

            print("\n" + "=" * 60)
            print("SUCCESS! Session saved for future use.")
            print(f"Next time: python login_permanent.py --resume")
            print(f"Session valid for ~2-4 weeks")
            print("=" * 60)
        else:
            print("\n[-] Login failed - check screenshots/")


if __name__ == "__main__":
    asyncio.run(main())
