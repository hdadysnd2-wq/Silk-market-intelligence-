// رُتبة ٣ — قفل مُعمَّم عبر عائلات منتجات حقيقية (الموجة ٤: ترحيل القائمة
// الرسمية الكاملة + عكس التدفّق — طلب المُشرِف). لكل منتج: يُضبَط عبر خطّاف
// الاختبار، يُنقَر «بحث عميق»، ثم صندوق حوار «تأكيد رمز HS» يظهر — أبداً
// «✓ صُنّف تلقائياً» — واختيار مرشّحٍ يُتابع التدفّق فعلياً.
//
// بلا مفتاح كلود (يُنزَع عمداً في كل e2e، LAW §2 — الدلو الثاني فقط): بعد
// عكس التدفّق (الموجة ٤)، القائمة المحلية **لا تقترح رمزاً تلقائياً أبداً**
// بمعزلٍ عن كلود — فالتلقائي الصارم مستحيلٌ بنيوياً في بيئةٍ بلا مفتاح، لكل
// منتجٍ بلا استثناء (لا فقط الغامض منها كما كان سابقاً). هذا القفل يثبت
// الآلية الحيّة (متصفّحٌ حقيقي) لثماني عائلاتٍ متنوّعة على التوالي — الحسم
// التلقائي الفعلي (اقتراح كلود يتجاوز عتبة الثقة) بوّابة المالك المدفوعة،
// ومُثبَتٌ هرمتياً بمحاكاة LLM في tests/test_hs_general_classifier.py.

const { chromium } = require("playwright");

const BASE = process.env.BASE_URL;
const MARKET = process.env.PRERUN_MARKET_ISO3 || "ARE";

if (!BASE) { console.error("MISSING BASE_URL env"); process.exit(2); }

const PRODUCTS = [
  "زبدة الفول السوداني", "مياه ورد", "عود معطر", "زيت زيتون",
  "تمر سكري", "عسل سدر", "شيبس بنكهة الجبن", "صودا كاوية",
];

const steps = [];
function ok(name, detail) { steps.push({ name, ok: true, detail: detail || "" }); }
function fail(name, detail) {
  steps.push({ name, ok: false, detail: detail || "" });
  throw new Error(`STEP FAILED: ${name} — ${detail || ""}`);
}

// يلي اختيار المرشّح احتمالُ نافذة استشارة بلد منشأٍ منفصلة تماماً (بوّابةٌ
// أخرى، بلا علاقة بهذا القفل) لبعض أزواج HS/سوق مبذورة. أغلقها إن ظهرت كي
// تتحرّر الحالة للجولة التالية، ولا تنتظرها إن لم تظهر.
async function settleAfterClassification(page) {
  try {
    await page.waitForSelector("#advOk", { timeout: 4000 });
    await page.locator("#advOk").click();
    await page.waitForFunction(() => !document.querySelector(".prov"), { timeout: 10000 });
  } catch (_) { /* لم تظهر استشارةٌ — طبيعيٌّ لأزواج HS/سوق غير مبذورة */ }
  await page.waitForFunction(() => {
    const b = document.querySelector("#researchBtn");
    return b && !b.disabled;
  }, { timeout: 15000 }).catch(() => {});
}

async function runCase(page, product) {
  // أعِد الحالة لكلّ جولة (بلا إعادة تحميل الصفحة — أسرع، ونفس نمط
  // __silkTestSetProduct الذي يصفّر S.hs/hsConfirmed/#pResolved أصلاً).
  await page.evaluate((name) => window.__silkTestSetProduct(name), product);
  ok(`${product}:product_set`);

  // نقرة صفّ السوق تُبدِّل التحديد (toggle) — انقر فقط إن لم يكن محدَّداً
  // أصلاً، وإلا تُلغي جولةٌ لاحقة تحديد جولةٍ سابقة (فخّ e2e لا فخّ منتج).
  const mrow = page.locator(`#marketBox .mrow[data-iso3="${MARKET}"]`);
  const anyMrow = (await mrow.count()) ? mrow.first()
    : page.locator("#marketBox .mrow").first();
  if (!(await anyMrow.evaluate((el) => el.classList.contains("sel")))) {
    await anyMrow.click();
  }
  ok(`${product}:market_selected`);

  await page.locator("#researchBtn").click();

  await page.waitForSelector(".prov", { timeout: 15000 });
  const dialogText = await page.locator(".prov").first().innerText();
  if (!/تأكيد رمز HS/.test(dialogText))
    fail(`${product}:candidates_modal`, `dialog missing heading: ${dialogText}`);
  if (/صُنّف تلقائياً/.test(dialogText))
    fail(`${product}:candidates_modal`,
      `dialog must never show the auto-classified checkmark: ${dialogText}`);
  const badgeText = await page.locator("#pResolved").innerText().catch(() => "");
  if (/صُنّف تلقائياً/.test(badgeText))
    fail(`${product}:no_auto_badge_behind_dialog`,
      `#pResolved shows the auto badge while a candidates dialog is open: ${badgeText}`);
  ok(`${product}:candidates_modal`, "blocking dialog shown, no auto-badge anywhere");

  const candCount = await page.locator(".hsCand").count();
  if (candCount < 1) fail(`${product}:candidates_present`, "no candidate buttons rendered");
  await page.locator(".hsCand").first().click();
  await page.waitForFunction(() => !document.querySelector(".prov"), { timeout: 15000 });
  ok(`${product}:candidate_selected`);
  await settleAfterClassification(page);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  try {
    await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForSelector("#marketBox .mrow", { timeout: 15000 });
    ok("dashboard_render");

    for (const product of PRODUCTS) {
      await runCase(page, product);
    }

    if (consoleErrors.length)
      fail("no_page_errors", consoleErrors.join(" | "));
    ok("no_page_errors");

    console.log(JSON.stringify({ result: "PASS", steps }, null, 2));
    console.log("HSTIERFAMILY PASS");
  } finally {
    await browser.close();
  }
}

main().catch((e) => {
  console.error(JSON.stringify({ result: "FAIL", steps }, null, 2));
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
});
