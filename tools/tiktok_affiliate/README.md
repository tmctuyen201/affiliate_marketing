# TikTok Affiliate Automation

## Status: 🚧 BLOCKED - Bot Detection

TikTok's login system detects headless browsers with:
- Visual CAPTCHA ("Select 2 objects with similar shapes")
- Rate limiting after multiple attempts
- JS fingerprinting (webdriver detection)

## Approach

### Working Strategy: Cookie Injection
1. **Manual login** on phone/real browser → export cookies
2. **Load cookies** into Playwright with stealth settings
3. **Extract** product affiliate links from dashboard
4. **Generate** content and post automatically

### Key Technical Details
- **Login URL**: `seller-vn.tiktok.com/account/login`
- **Country**: Vietnam (+84) - must manually select in dropdown
- **Dropdown trick**: Click `[class*="AreaSelection"]` → scroll to "Vietnam +84" → click
- **Password mode**: Click "Đăng nhập bằng mật khẩu" to switch from SMS
- **Rate limit**: ~5 attempts before "Đã đạt số lần thử tối đa"

### Anti-Detection Settings
```python
# These work for page loading but NOT for login
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0"
viewport = {"width": 1366, "height": 768}
locale = "vi-VN"
timezone = "Asia/Ho_Chi_Minh"
args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
```

### Internal APIs (for data extraction after login)
- `__UNIVERSAL_DATA_FOR_REHYDRATION__` - embedded product data in page HTML
- `/api/reflow/recommend/item_list` - product anchors from video pages

## Files
- `login.py` - Main login + extraction script
- `cookies.json` - Saved session cookies (gitignored)
- `screenshots/` - Debug screenshots (gitignored)

## Next Steps
1. [ ] User logs in manually and exports cookies
2. [ ] Test cookie-based login works
3. [ ] Build affiliate link extractor
4. [ ] Integrate with content generator
5. [ ] Add to daily cron pipeline

## References
- [amsaxx19/Tiktok-Automation-API](https://github.com/amsaxx19/Tiktok-Automation-API) - Working Playwright-based scraper
- TikTok Open API: `open.tiktokapis.com` (requires partner registration)
