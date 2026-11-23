#!/usr/bin/env node
/**
 * مملكة الأسرار - Amazon corner (Creators API, Node 18+, NO dependencies).
 *
 * Always creates deals/index.html ("ركن أمازون"): category tiles with affiliate SEARCH links (work without the API, show no prices).
 * When the Creators API is available for your account it also adds today's products (deals/<ASIN>.html) above the tiles.
 *
 * IMPORTANT: Amazon retired PA-API 5 (the old paapi5-nodejs-sdk now gets HTTP 403). The replacement is the Creators API:
 * OAuth 2.0 credentials (Credential ID + Secret + Version) from Associates Central > Tools > Creators API.
 * HTTP 403 "AssociateNotEligible" means Amazon has not enabled the API for the account yet: this is tolerated (warning, no red job).
 *
 * Env: AMAZON_CREDENTIAL_ID, AMAZON_CREDENTIAL_SECRET, AMAZON_CREDENTIAL_VERSION (default 3.1 = North America, 3.2 = EU, 3.3 = Far East),
 *      AMAZON_TRACKING_ID (your Associate tag), AMAZON_MARKETPLACE (default www.amazon.com),
 *      optional: AMAZON_TOKEN_URL, AMAZON_TOKEN_SCOPE
 * Test without calling Amazon:  node amazon_products.js --mock sample.json
 */
const fs = require('fs');
const path = require('path');

const E = process.env;
// GitHub secrets often carry a hidden trailing newline (\r\n) when pasted: strip ALL whitespace from every setting.
const clean = (v) => String(v ?? '').replace(/\s+/g, '');
const MARKETPLACE = clean(E.AMAZON_MARKETPLACE) || 'www.amazon.com';
const PARTNER_TAG = clean(E.AMAZON_TRACKING_ID);
const CRED_ID = clean(E.AMAZON_CREDENTIAL_ID);
const CRED_SECRET = clean(E.AMAZON_CREDENTIAL_SECRET);
const VERSION = clean(E.AMAZON_CREDENTIAL_VERSION) || '3.1';
const API = 'https://creatorsapi.amazon/catalog/v1/searchItems';
const TOKEN_URLS = {
  '3.1': 'https://api.amazon.com/auth/o2/token',
  '3.2': 'https://api.amazon.co.uk/auth/o2/token',
  '3.3': 'https://api.amazon.co.jp/auth/o2/token',
};
const OUT = path.join(__dirname, 'deals');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---- season / topic (same logic as your original script)
function topic(now = new Date()) {
  const m = now.getMonth() + 1;
  if (m >= 6 && m <= 8) return { keywords: 'Casual Summer Fashion tops shorts', name: 'موضة صيفية وتخفيضات', index: 'Apparel' };
  if (m === 12 || m <= 2) return { keywords: 'Unisex Winter jackets warm hoodies', name: 'موضة شتوية دافئة', index: 'Apparel' };
  if (m === 9) return { keywords: 'School backpacks students ergonomic', name: 'مستلزمات مدرسية وكتب', index: 'All' };
  return now.getDate() % 2 === 0
    ? { keywords: 'PlayStation Xbox Gift Cards digital', name: 'تكنولوجيا وألعاب', index: 'VideoGames' }
    : { keywords: 'Bestselling self development growth books', name: 'ثقافة وكتب', index: 'Books' };
}

// ---- helpers that tolerate camelCase / PascalCase differences in the response
const get = (o, ...paths) => {
  for (const p of paths) {
    let v = o;
    for (const k of p.split('.')) {
      if (v == null) break;
      const alt = k.charAt(0).toUpperCase() + k.slice(1);
      v = v[k] !== undefined ? v[k] : v[alt];
    }
    if (v != null && v !== '') return v;
  }
  return undefined;
};

async function getToken() {
  if (!CRED_ID || !CRED_SECRET) throw new Error('Missing AMAZON_CREDENTIAL_ID / AMAZON_CREDENTIAL_SECRET (Creators API credentials, not the old AWS keys)');
  const url = clean(E.AMAZON_TOKEN_URL) || TOKEN_URLS[VERSION];
  if (!url) throw new Error(`Credential version ${VERSION}: set AMAZON_TOKEN_URL (Cognito token URL shown in Associates Central)`);
  const v3 = VERSION.startsWith('3');
  const scope = (E.AMAZON_TOKEN_SCOPE || '').trim() || (v3 ? 'creatorsapi::default' : 'creatorsapi/default');
  const res = await fetch(url, v3
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ grant_type: 'client_credentials', client_id: CRED_ID, client_secret: CRED_SECRET, scope }) }
    : { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ grant_type: 'client_credentials', client_id: CRED_ID, client_secret: CRED_SECRET, scope }) });
  const j = await res.json().catch(() => ({}));
  if (!res.ok || !j.access_token) throw new Error(`Token request failed (HTTP ${res.status}): ${JSON.stringify(j).slice(0, 300)}`);
  return j.access_token;
}

async function searchItems(t) {
  if (!PARTNER_TAG) throw new Error('AMAZON_TRACKING_ID is empty (your Associate tag, e.g. mysite-20)');
  const token = await getToken();
  const res = await fetch(API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: VERSION.startsWith('2') ? `Bearer ${token}, Version ${VERSION}` : `Bearer ${token}`,
      'x-marketplace': MARKETPLACE,
    },
    body: JSON.stringify({
      keywords: t.keywords, searchIndex: t.index, itemCount: 3, sortBy: 'AvgCustomerReviews',
      partnerTag: PARTNER_TAG, marketplace: MARKETPLACE,
      resources: ['images.primary.large', 'itemInfo.title', 'offersV2.listings.price'],
    }),
  });
  const j = await res.json().catch(() => ({}));
  if (res.status === 403 && /AssociateNotEligible/i.test(JSON.stringify(j))) {
    const err = new Error('Amazon: this Associates account does not currently meet the Creators API eligibility requirements');
    err.notEligible = true;
    throw err;
  }
  if (!res.ok) throw new Error(`SearchItems failed (HTTP ${res.status}): ${JSON.stringify(j).slice(0, 400)}`);
  return j;
}

function normalize(item) {
  const price = get(item, 'offersV2.listings.0.price.money.displayAmount', 'offersV2.listings.0.price.displayAmount',
    'offers.listings.0.price.displayAmount') || '';
  return {
    asin: String(get(item, 'asin') || '').replace(/[^A-Za-z0-9]/g, ''),
    title: get(item, 'itemInfo.title.displayValue') || '',
    image: get(item, 'images.primary.large.url') || '',   // Amazon's own image URL, used exactly as returned (no changes)
    url: get(item, 'detailPageURL') || '',
    price,
  };
}

const stamp = () => new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

const CSS = `*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Tahoma,'Segoe UI',system-ui,sans-serif;line-height:1.9;color:#e9dfc8;background:radial-gradient(circle at 15% -10%,#3a2f18 0,transparent 45%),radial-gradient(circle at 85% 110%,#241d10 0,transparent 50%),#0b0b0d;background-attachment:fixed;min-height:100vh}
.wrap{max-width:900px;margin:0 auto;padding:22px 16px 48px}.top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:18px;font-weight:700;font-size:14px}
.top a{color:#e6c473;text-decoration:none;border-bottom:1px solid rgba(230,196,115,.35);padding-bottom:2px;transition:.2s}.top a:hover{color:#fff3cf;border-color:#f6d98a}
.card{position:relative;background:linear-gradient(160deg,rgba(28,26,23,.96),rgba(14,14,16,.98));border:1px solid #8a6f37;border-radius:18px;padding:26px;box-shadow:0 18px 50px rgba(0,0,0,.55),inset 0 0 0 1px rgba(246,217,138,.08)}
.card:before{content:'✦';position:absolute;top:10px;left:18px;color:rgba(230,196,115,.35);font-size:18px}
h1{font-size:clamp(22px,5vw,32px);line-height:1.5;margin:0 0 14px;padding:0 0 12px;border-bottom:1px solid transparent;border-image:linear-gradient(90deg,#f6d98a,#8a6f37,transparent) 1;font-weight:700;color:#f7e7b7;letter-spacing:.3px;text-shadow:0 2px 14px rgba(230,196,115,.25)}
h2{color:#efd797}.note{font-size:13px;color:#cfc4ad;background:rgba(230,196,115,.07);border-right:3px solid #c9a24c;border-radius:8px;padding:11px 15px;margin:0 0 18px}
.box{display:flex;gap:20px;align-items:center;flex-wrap:wrap;border:1px solid rgba(230,196,115,.28);border-radius:14px;padding:18px;margin:16px 0;background:rgba(255,255,255,.02)}
.box img{width:min(220px,100%);height:auto;border-radius:10px;margin:0 auto;display:block;background:#fff}.box .info{flex:1;min-width:230px}
.price{color:#f5cf72;font-weight:700;font-size:21px;margin:6px 0;text-shadow:0 0 12px rgba(245,207,114,.3)}.small{display:block;font-size:12px;color:#a89c84;line-height:1.7;margin:6px 0 12px}
.btn{display:inline-block;background:linear-gradient(180deg,#f7dd93,#d4ac50);border:1px solid #f7e7b7;color:#201804;padding:12px 24px;border-radius:30px;font-weight:700;text-decoration:none;box-shadow:0 6px 18px rgba(212,172,80,.25)}.btn:hover{filter:brightness(1.08)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}.item{display:block;background:linear-gradient(160deg,rgba(40,36,28,.85),rgba(18,18,20,.95));border:1px solid rgba(230,196,115,.28);border-radius:14px;padding:16px;text-decoration:none;color:#eadfc6;transition:transform .2s,border-color .2s,box-shadow .2s}
.item:hover{transform:translateY(-4px);border-color:#e6c473;box-shadow:0 12px 26px rgba(0,0,0,.5),0 0 0 1px rgba(246,217,138,.2)}
.item img{width:100%;height:180px;object-fit:contain;background:#fff;border-radius:8px;padding:6px}.item b{display:block;font-size:15px;line-height:1.7;margin-top:10px;color:#f4e4ba}
.cat{text-align:center}.cat .ico{font-size:40px;display:block;filter:drop-shadow(0 3px 8px rgba(230,196,115,.35))}`;

const DISCLOSURE = `<p class="note">إفصاح: هذه الصفحة تحتوي على روابط تابعة (Affiliate). بصفتنا شركاء في برنامج Amazon Associates قد نحصل على عمولة من المشتريات المؤهلة دون أي تكلفة إضافية عليك.<br>
<span dir="ltr">As an Amazon Associate I earn from qualifying purchases.</span></p>`;

function page(p, t, when) {
  const priceHtml = p.price
    ? `<div class="price">${esc(p.price)}</div>
<span class="small" dir="ltr">Amazon prices are subject to change. Price as of ${esc(when)}.</span>`
    : `<span class="small">السعر الحالي وتوفر المنتج يظهران في صفحة المنتج على أمازون.</span>`;
  return `<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(p.title)} | مملكة الأسرار</title><meta name="description" content="${esc(p.title)} - اختيار من قسم ${esc(t.name)} على أمازون.">
<meta name="robots" content="noindex,follow"><style>${CSS}</style></head><body><div class="wrap">
<div class="top"><a href="../index.html">← مملكة الأسرار</a><a href="index.html">كل العروض</a></div>
<div class="card">${DISCLOSURE}<h1>${esc(p.title)}</h1>
<p>منتج من قسم <b>${esc(t.name)}</b>، ظهر ضمن أعلى النتائج على أمازون عند الترتيب حسب تقييمات العملاء. التقييمات والمواصفات الكاملة والآراء الحقيقية للمشترين متاحة في صفحة المنتج على أمازون.</p>
<div class="box"><img src="${esc(p.image)}" alt="${esc(p.title)}" loading="lazy" decoding="async">
<div class="info"><h2 style="font-size:17px;margin:0">${esc(p.title)}</h2>${priceHtml}
<a class="btn" href="${esc(p.url)}" target="_blank" rel="sponsored nofollow noopener noreferrer">عرض على أمازون</a></div></div>
</div></div></body></html>`;
}

// ---- category tiles: affiliate SEARCH links (no API needed, no prices shown, so nothing can become stale)
function tiles(t) {
  const fixed = [
    ['🧥', 'ملابس وجاكيتات', 'jackets hoodies clothing'], ['📚', 'كتب الأكثر مبيعًا', 'bestselling books'],
    ['🎮', 'ألعاب وبطاقات رقمية', 'PlayStation Xbox gift cards'], ['🎒', 'حقائب مدرسية وسفر', 'backpacks'],
    ['🎧', 'سماعات وإلكترونيات', 'headphones electronics'], ['🏠', 'المنزل والمطبخ', 'home kitchen'],
    ['💄', 'العناية والجمال', 'skincare beauty'], ['💪', 'الرياضة واللياقة', 'fitness sports'],
  ];
  const all = [['⭐', 'اختيار الموسم: ' + t.name, t.keywords], ...fixed];
  return `<div class="grid">` + all.map(([ico, name, q]) =>
    `<a class="item cat" href="https://${esc(MARKETPLACE)}/s?k=${encodeURIComponent(q)}&amp;tag=${encodeURIComponent(PARTNER_TAG)}" target="_blank" rel="sponsored nofollow noopener noreferrer"><span class="ico">${ico}</span><b>${esc(name)}</b><span class="small">تصفّح على أمازون ←</span></a>`).join('') + `</div>`;
}

function indexPage(list, t, when) {
  const products = list.length
    ? `<h2 style="font-size:19px">اختيارات اليوم</h2><div class="grid">` + list.map((p) => `<a class="item" href="${p.asin}.html"><img src="${esc(p.image)}" alt="${esc(p.title)}" loading="lazy" decoding="async"><b>${esc(p.title)}</b>${p.price ? `<span class="price">${esc(p.price)}</span>` : ''}</a>`).join('') + `</div>
<span class="small" dir="ltr">Amazon prices are subject to change. Price as of ${esc(when)}.</span>`
    : '';
  return `<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ركن أمازون | مملكة الأسرار</title><meta name="robots" content="noindex,follow"><style>${CSS}</style></head><body><div class="wrap">
<div class="top"><a href="../index.html">← مملكة الأسرار</a></div>
<div class="card">${DISCLOSURE}<h1>ركن أمازون</h1>
<p>اختر القسم الذي يهمّك وتصفّح المنتجات مباشرة على أمازون. الأسعار والتقييمات وتوفر المنتجات تظهر في أمازون وقت الشراء.</p>
${products}<h2 style="font-size:19px;margin-top:22px">تصفّح الأقسام</h2>${tiles(t)}</div></div></body></html>`;
}

async function main() {
  if (!PARTNER_TAG) throw new Error('AMAZON_TRACKING_ID is empty (your Associate tag, e.g. mysite-20)');
  const t = topic();
  const mi = process.argv.indexOf('--mock');
  let list = [], eligible = true, problem = '';
  try {
    const data = mi > -1 ? JSON.parse(fs.readFileSync(process.argv[mi + 1], 'utf8')) : await searchItems(t);
    const items = get(data, 'searchResult.items') || [];
    list = items.map(normalize).filter((p) => p.asin && p.title && p.image && p.url);
    if (!list.length) throw new Error('No usable products returned: ' + JSON.stringify(data).slice(0, 300));
  } catch (e) {
    if (!e.notEligible) throw e;   // real errors still fail the job; only "account not eligible" is tolerated
    eligible = false;
    problem = e.message;
  }
  const when = stamp();
  fs.mkdirSync(OUT, { recursive: true });
  for (const f of fs.readdirSync(OUT)) if (f.endsWith('.html')) fs.unlinkSync(path.join(OUT, f));   // never keep stale prices
  for (const p of list) {
    fs.writeFileSync(path.join(OUT, `${p.asin}.html`), page(p, t, when));
    console.log('page written:', p.asin, '-', p.title.slice(0, 60));
  }
  fs.writeFileSync(path.join(OUT, 'index.html'), indexPage(list, t, when));
  if (!eligible) {
    console.log('::warning::' + problem + '. Product pages are skipped until Amazon enables the Creators API for this account (Associates Central > Tools > Creators API). The category page (affiliate search links) was still created.');
  }
  console.log(`done: ${list.length} products + category page, price time ${when}`);
}

main().catch((e) => { console.error('amazon_products failed:', e.message); process.exit(1); });
