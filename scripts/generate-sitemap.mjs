import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const siteOrigin = "https://cartaway.it";
const catalogUrl = new URL("../data/products.json", import.meta.url);
const siteUrl = new URL("../data/site.json", import.meta.url);
const sitemapUrl = new URL("../sitemap.xml", import.meta.url);
const templateUrl = new URL("../prodotto.html", import.meta.url);
const productPagesDirectory = fileURLToPath(new URL("../prodotti/", import.meta.url));
const [catalog, site, template] = await Promise.all([
  readFile(catalogUrl, "utf8").then(JSON.parse),
  readFile(siteUrl, "utf8").then(JSON.parse),
  readFile(templateUrl, "utf8"),
]);

if (!Array.isArray(catalog.products)) {
  throw new TypeError("data/products.json deve contenere un array products.");
}

const products = catalog.products.filter((product) => product && product.available !== false);
const productIds = new Set();
for (const product of products) {
  if (typeof product.id !== "string" || !/^[a-zA-Z0-9_-]+$/.test(product.id)) {
    throw new TypeError(`ID prodotto non valido per la pagina statica: ${product.id}`);
  }
  if (productIds.has(product.id)) {
    throw new TypeError(`ID prodotto duplicato: ${product.id}`);
  }
  productIds.add(product.id);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function replaceMetaContent(html, attribute, key, value) {
  const pattern = new RegExp(`<meta\\b(?=[^>]*\\b${escapeRegExp(attribute)}="${escapeRegExp(key)}")[^>]*>`, "i");
  const match = html.match(pattern);
  if (!match) throw new Error(`Meta tag non trovato: ${attribute}=${key}`);
  const updatedTag = match[0].replace(/\bcontent="[^"]*"/i, `content="${escapeHtml(value)}"`);
  return html.replace(pattern, () => updatedTag);
}

function replaceElementContent(html, id, content) {
  const pattern = new RegExp(`(<([a-z][a-z0-9:-]*)\\b(?=[^>]*\\bid="${escapeRegExp(id)}")[^>]*>)[\\s\\S]*?(</\\2>)`, "i");
  const match = html.match(pattern);
  if (!match) throw new Error(`Elemento HTML non trovato: ${id}`);
  return html.replace(pattern, (_fullMatch, openingTag, tagName) => `${openingTag}${content}</${tagName}>`);
}

function updateElementAttributes(html, id, attributes) {
  const pattern = new RegExp(`<([a-z][a-z0-9:-]*)\\b(?=[^>]*\\bid="${escapeRegExp(id)}")[^>]*>`, "i");
  const match = html.match(pattern);
  if (!match) throw new Error(`Elemento HTML non trovato: ${id}`);
  const updatedTag = Object.entries(attributes).reduce((tag, [name, value]) => {
    const attributePattern = new RegExp(`\\b${escapeRegExp(name)}="[^"]*"`, "i");
    const replacement = `${name}="${escapeHtml(value)}"`;
    return attributePattern.test(tag)
      ? tag.replace(attributePattern, replacement)
      : tag.replace(/\s*\/?>$/, (ending) => ` ${replacement}${ending}`);
  }, match[0]);
  return html.replace(pattern, () => updatedTag);
}

function setElementVisible(html, id) {
  const pattern = new RegExp(`<([a-z][a-z0-9:-]*)\\b(?=[^>]*\\bid="${escapeRegExp(id)}")[^>]*>`, "i");
  const match = html.match(pattern);
  if (!match) throw new Error(`Elemento HTML non trovato: ${id}`);
  const updatedTag = match[0].replace(/\s+hidden(?:\s*=\s*(?:"[^"]*"|'[^']*'))?(?=\s|\/?>)/i, "");
  return html.replace(pattern, () => updatedTag);
}

function productPageUrl(productId) {
  return new URL(`/prodotti/${encodeURIComponent(productId)}/`, siteOrigin).href;
}

function productCategories(category) {
  const values = Array.isArray(category) ? category : [category];
  return values
    .flatMap((value) => typeof value === "string" ? value.split(" / ") : [])
    .map((value) => value.trim())
    .filter(Boolean);
}

function productUnitLabel(unit) {
  if (!unit || typeof unit !== "object" || Array.isArray(unit)) return "";
  const quantity = unit.quantity === null || unit.quantity === undefined || unit.quantity === ""
    ? ""
    : new Intl.NumberFormat("it-IT", { maximumFractionDigits: 3 }).format(Number(unit.quantity));
  const measure = String(unit.measure || "").trim();
  const primary = quantity && measure ? `${quantity} ${measure}` : "";
  const details = String(unit.details || "").trim();
  return [primary, details].filter(Boolean).join(" · ");
}

function configuredCategoryPath(siteConfig, path) {
  const categories = Array.isArray(siteConfig.categories) ? siteConfig.categories : [];
  const flatCategory = categories.find((category) =>
    category && typeof category === "object" && category.name === path.join(" / "));
  if (flatCategory) return [flatCategory];
  let currentCategories = categories;
  const matchedCategories = [];
  for (const name of path) {
    const currentCategory = currentCategories.find((category) =>
      category && typeof category === "object" && category.name === name);
    if (!currentCategory) return [];
    matchedCategories.push(currentCategory);
    currentCategories = Array.isArray(currentCategory.children) ? currentCategory.children : [];
  }
  return matchedCategories;
}

function productVatRate(siteConfig, product) {
  const categories = configuredCategoryPath(siteConfig, productCategories(product.category));
  for (let index = categories.length - 1; index >= 0; index -= 1) {
    const value = categories[index].vat_rate;
    if (value === null || value === undefined || (typeof value === "string" && !value.trim())) continue;
    const rate = Number(value);
    return Number.isFinite(rate) && rate >= 0 && rate <= 100 ? rate : null;
  }
  return null;
}

function productPriceInCents(siteConfig, product) {
  const amount = Number(product.price);
  const price = Number.isFinite(amount) ? Math.round(amount * 100) : 0;
  if (siteConfig.prices_include_vat !== false) return price;
  const rate = productVatRate(siteConfig, product);
  return rate === null ? null : price + Math.round(price * rate / 100);
}

function safeProductImage(value) {
  const fallback = "https://images.unsplash.com/photo-1608494133726-bb93324274c8?auto=format&fit=crop&w=900&q=82";
  if (typeof value !== "string" || !value.trim()) return fallback;
  try {
    const url = new URL(value.trim(), siteOrigin);
    return url.origin === siteOrigin || url.protocol === "https:" ? url.href : fallback;
  } catch {
    return fallback;
  }
}

function normalizeDescription(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= 160) return text;
  const shortened = text.slice(0, 157);
  const lastSpace = shortened.lastIndexOf(" ");
  return `${shortened.slice(0, lastSpace > 0 ? lastSpace : shortened.length).trim()}...`;
}

function productNameWithFormat(product) {
  const name = String(product.name || "Prodotto").trim();
  const unitLabel = productUnitLabel(product.unit);
  const primaryFormat = unitLabel.split(" · ")[0].trim();
  return !primaryFormat || name.toLowerCase().includes(primaryFormat.toLowerCase())
    ? name
    : `${name} ${unitLabel}`;
}

function renderProductPage(product) {
  const productName = String(product.name || "Prodotto").trim();
  const productNameForMetadata = productNameWithFormat(product);
  const productUrl = productPageUrl(product.id);
  const productUnit = productUnitLabel(product.unit);
  const categoryPath = productCategories(product.category);
  const description = String(product.description || "").trim();
  const images = [...new Set([product.image, ...(Array.isArray(product.images) ? product.images : [])]
    .map((image) => typeof image === "string" ? image.trim() : "")
    .filter(Boolean))].map(safeProductImage);
  const productPriceCents = productPriceInCents(site, product);
  const formatPrice = (cents) => new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(cents / 100);
  const priceText = productPriceCents === null
    ? "Aliquota IVA da configurare"
    : formatPrice(productPriceCents);
  const city = String(site.city || "").trim();
  const metaDescription = normalizeDescription([
    `${productNameForMetadata}.`,
    description || "Scopri dettagli e caratteristiche del prodotto.",
    city ? `Consegna a ${city} e nei comuni vicini.` : "Consegna nelle zone configurate.",
  ].join(" "));
  const specifications = Array.isArray(product.specifications)
    ? product.specifications.filter((item) => String(item.label || "").trim() && String(item.value || "").trim())
    : [];
  const specificationHtml = specifications.map((item) =>
    `<dt>${escapeHtml(String(item.label).trim())}</dt><dd>${escapeHtml(String(item.value).trim())}</dd>`).join("");
  const allVatRatesConfigured = Array.isArray(site.categories)
    && site.categories.length > 0
    && catalog.products.length > 0
    && catalog.products.every((item) => productVatRate(site, item) !== null);
  const vatStatus = site.prices_include_vat !== false
    ? "IVA inclusa"
    : allVatRatesConfigured
      ? "IVA aggiunta in base alla categoria"
      : "IVA esclusa - aliquote da configurare";
  const productSchema = {
    "@context": "https://schema.org",
    "@graph": [
      ...(productPriceCents === null ? [] : [{
        "@type": "Product",
        "@id": `${productUrl}#product`,
        name: productNameForMetadata,
        url: productUrl,
        ...(categoryPath.length ? { category: categoryPath.join(", ") } : {}),
        ...(description ? { description } : {}),
        ...(images.length ? { image: images } : {}),
        ...(specifications.length ? {
          additionalProperty: specifications.map((item) => ({
            "@type": "PropertyValue",
            name: String(item.label).trim(),
            value: String(item.value).trim(),
          })),
        } : {}),
        offers: {
          "@type": "Offer",
          url: productUrl,
          priceCurrency: "EUR",
          price: productPriceCents / 100,
          availability: "https://schema.org/InStock",
        },
      }]),
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Catalogo", item: `${siteOrigin}/` },
          { "@type": "ListItem", position: 2, name: productName, item: productUrl },
        ],
      },
    ],
  };
  const serializedSchema = JSON.stringify(productSchema).replace(/</g, "\\u003c");
  let html = template;
  html = html.replace(/<title>[\s\S]*?<\/title>/i, () => `<title>${escapeHtml(`${productNameForMetadata} | ${site.brand || "Cartaway"}`)}</title>`);
  html = replaceMetaContent(html, "name", "description", metaDescription);
  html = replaceMetaContent(html, "property", "og:url", productUrl);
  html = replaceMetaContent(html, "property", "og:title", `${productNameForMetadata} | ${site.brand || "Cartaway"}`);
  html = replaceMetaContent(html, "property", "og:description", metaDescription);
  html = replaceMetaContent(html, "property", "og:site_name", site.brand || "Cartaway");
  html = replaceMetaContent(html, "property", "og:image", images[0] || "");
  html = replaceMetaContent(html, "property", "og:image:alt", productNameForMetadata);
  html = replaceMetaContent(html, "name", "twitter:title", `${productNameForMetadata} | ${site.brand || "Cartaway"}`);
  html = replaceMetaContent(html, "name", "twitter:description", metaDescription);
  html = replaceMetaContent(html, "name", "twitter:image", images[0] || "");
  html = replaceMetaContent(html, "name", "twitter:image:alt", productNameForMetadata);
  const canonicalMarker = "<!-- PRODUCT_CANONICAL -->";
  if (!html.includes(canonicalMarker)) throw new Error("Segnaposto canonical prodotto non trovato.");
  html = html.replace(canonicalMarker, () => `<link rel="canonical" href="${escapeHtml(productUrl)}" />`);
  const schemaPattern = /(<script id="seo-structured-data" type="application\/ld\+json">)[\s\S]*?(<\/script>)/;
  if (!schemaPattern.test(html)) throw new Error("Script JSON-LD prodotto non trovato.");
  html = html.replace(schemaPattern, (_match, openingTag, closingTag) => `${openingTag}\n      ${serializedSchema}\n    ${closingTag}`);
  html = replaceElementContent(html, "detail-category", escapeHtml(categoryPath.at(-1) || "Carta"));
  html = replaceElementContent(html, "detail-title", escapeHtml(productName));
  html = replaceElementContent(html, "detail-unit", escapeHtml(productUnit));
  html = replaceElementContent(html, "detail-price", escapeHtml(priceText));
  html = replaceElementContent(html, "detail-description", escapeHtml(description));
  html = replaceElementContent(html, "detail-breadcrumb-title", escapeHtml(productName));
  html = replaceElementContent(html, "detail-specifications", specificationHtml);
  html = replaceElementContent(html, "detail-unit-price", "");
  html = replaceElementContent(html, "detail-vat-status", escapeHtml(vatStatus));
  html = updateElementAttributes(html, "detail-image", {
    src: images[0] || safeProductImage(""),
    alt: `${productName}, foto 1`,
  });
  html = setElementVisible(html, "product-detail");
  if (specifications.length) html = setElementVisible(html, "detail-specifications-section");
  const quantity = Number(product.unit?.quantity);
  if (productPriceCents !== null && Number.isFinite(quantity) && quantity > 1) {
    const unitPrice = Math.round(productPriceCents / quantity);
    html = replaceElementContent(html, "detail-unit-price", `${escapeHtml(formatPrice(unitPrice))} / ${escapeHtml(String(product.unit.pricePer || ""))}`);
    html = setElementVisible(html, "detail-unit-price-wrap");
  }
  return html;
}

await rm(productPagesDirectory, { recursive: true, force: true });
await mkdir(productPagesDirectory, { recursive: true });
await Promise.all(products.map((product) => {
  const outputDirectory = join(productPagesDirectory, product.id);
  return mkdir(outputDirectory, { recursive: true })
    .then(() => writeFile(join(outputDirectory, "index.html"), renderProductPage(product), "utf8"));
}));

const staticUrls = [
  `${siteOrigin}/`,
  `${siteOrigin}/chi-siamo.html`,
  `${siteOrigin}/primi-passi.html`,
  `${siteOrigin}/faq.html`,
];
const productUrls = products.map((product) => productPageUrl(product.id));
const urls = [...new Set([...staticUrls, ...productUrls])];
const entries = urls
  .map((url) => `  <url><loc>${url.replaceAll("&", "&amp;")}</loc></url>`)
  .join("\n");
const sitemap = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  entries,
  "</urlset>",
  "",
].join("\n");

await writeFile(sitemapUrl, sitemap, "utf8");
console.log(`Generate ${products.length} pagine prodotto statiche e una sitemap con ${urls.length} URL canonici.`);