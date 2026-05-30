"""
TikTok Affiliate Login & Product Link Extractor
================================================
Automates login to TikTok Shop Affiliate Center (seller-vn.tiktok.com)
and extracts product affiliate links.

STATUS: Blocked by TikTok's bot detection (captcha + rate limiting)
SOLUTION: Cookie injection from manual login session

Usage:
    python login.py                    # Interactive login attempt
    python login.py --cookies cookies.json  # Login with saved cookies

Requirements:
    pip install playwright
    playwright install chromium
"""

from playwright.sync_api import sync_playwright
import json
import sys
import argparse
from pathlib import Path

PHONE = "0902018245"
COUNTRY_CODE = "VN +84"
SELLER_URL = "https://seller-vn.tiktok.com"
LOGIN_URL = f"{SELLER_URL}/account/login"
AFFILIATE_URL = f"{SELLER_URL}/affiliate"
AFFILIATE_PRODUCT_URL = f"{SELLER_URL}/affiliate/product"

COOKIES_PATH = Path(__file__).parent / "cookies.json"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"


def create_browser_context(playwright, cookies_path=None):
    """Create a stealth browser context with mobile UA."""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
    """)

    if cookies_path and Path(cookies_path).exists():
        with open(cookies_path) as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print(f"[✓] Loaded {len(cookies)} cookies from {cookies_path}")

    return browser, context


def dismiss_cookie_banner(page):
    """Remove TikTok's cookie consent banner."""
    page.evaluate("""
        () => {
            const b = document.querySelector('tiktok-cookie-banner');
            if (b) b.remove();
        }
    """)


def select_vietnam_country(page):
    """Open country dropdown and select Vietnam +84."""
    country_el = page.evaluate("""
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

    page.mouse.click(country_el['x'], country_el['y'])
    page.wait_for_timeout(2000)

    clicked = page.evaluate("""
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
    page.wait_for_timeout(2000)
    return clicked


def login_with_credentials(page, phone, password):
    """Login with phone number and password."""
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    dismiss_cookie_banner(page)

    page.locator("span:has-text('Đăng nhập bằng tài khoản TikTok')").first.click(force=True)
    page.wait_for_timeout(8000)
    dismiss_cookie_banner(page)

    page.locator("text=Sử dụng số điện thoại/email/tên người dùng").first.click(force=True)
    page.wait_for_timeout(3000)

    select_vietnam_country(page)

    phone_input = page.locator("input[name='mobile']")
    phone_input.first.click(force=True)
    page.keyboard.type(phone, delay=80)
    page.wait_for_timeout(500)

    pwd_link = page.locator("text=Đăng nhập bằng mật khẩu")
    if pwd_link.count() > 0:
        pwd_link.first.click(force=True)
        page.wait_for_timeout(2000)

    pwd_input = page.locator("input[type='password']")
    pwd_input.first.click(force=True)
    page.keyboard.type(password, delay=80)
    page.wait_for_timeout(1000)

    page.screenshot(path=str(SCREENSHOTS_DIR / "before_login.png"))

    login_btn = page.locator("button:has-text('Đăng nhập')")
    for btn in login_btn.all():
        try:
            if btn.is_visible():
                btn.click(force=True)
                break
        except:
            continue

    page.wait_for_timeout(10000)
    page.screenshot(path=str(SCREENSHOTS_DIR / "after_login.png"))
    body = page.inner_text("body")[:500]

    if "captcha" in body.lower():
        print("[!] CAPTCHA detected - manual intervention needed")
        return False
    if "đã đạt" in body.lower():
        print("[!] Rate limited - wait 15-30 minutes")
        return False
    if "seller-vn.tiktok.com" in page.url and "login" not in page.url:
        print("[✓] Login successful!")
        return True

    print(f"[?] Unknown state: {page.url}")
    return False


def extract_affiliate_links(page):
    """Navigate to affiliate product page and extract links."""
    page.goto(AFFILIATE_PRODUCT_URL, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    products = page.evaluate("""
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
                                    image: obj.cover_url || obj.image || ''
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
        print(f"[✓] Found {len(products)} products from rehydration data")
        return products

    products = page.evaluate("""
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


def save_cookies(context, path):
    """Save browser cookies to file."""
    cookies = context.cookies()
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"[✓] Saved {len(cookies)} cookies to {path}")


def main():
    parser = argparse.ArgumentParser(description="TikTok Affiliate Login")
    parser.add_argument("--cookies", type=str, help="Path to cookies JSON file")
    parser.add_argument("--phone", type=str, default=PHONE)
    parser.add_argument("--password", type=str, help="Account password")
    parser.add_argument("--extract", action="store_true", help="Extract affiliate links after login")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser, context = create_browser_context(p, args.cookies)
        page = context.new_page()

        if args.cookies and Path(args.cookies).exists():
            page.goto(AFFILIATE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            if "login" in page.url.lower():
                print("[!] Cookies expired, need fresh login")
            else:
                print("[✓] Cookies valid!")
        elif args.password:
            login_with_credentials(page, args.phone, args.password)
            save_cookies(context, str(COOKIES_PATH))
        else:
            print("[!] Provide --cookies or --password")
            browser.close()
            return

        if args.extract:
            products = extract_affiliate_links(page)
            output_path = Path(__file__).parent / "affiliate_products.json"
            with open(output_path, "w") as f:
                json.dump(products, f, indent=2, ensure_ascii=False)
            print(f"[✓] Saved to {output_path}")

        save_cookies(context, str(COOKIES_PATH))
        browser.close()


if __name__ == "__main__":
    main()
