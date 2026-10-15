const cartStorageKey = "cartaway-cart-v1";
const fallbackImage =
  "https://images.unsplash.com/photo-1608494133726-bb93324274c8?auto=format&fit=crop&w=900&q=82";
const euro = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
});
const unitNumber = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 3 });

const state = {
  page: document.body.dataset.page || "home",
  products: [],
  site: {},
  orderSubmitting: false,
  cart: readCart(),
  sharedOrder: null,
  sharedSheet: null,
  openSharedCart: false,
  sheetQuantities: {},
  category: "tutte",
  profile: "tutte",
  categorySubcategoriesExpanded: false,
  search: "",
  sort: "featured",
  view: "grid",
  dialogProduct: null,
  dialogImages: [],
  dialogImageIndex: 0,
  detailProduct: null,
  detailImages: [],
  detailImageIndex: 0,
  deliveryMap: null,
  deliveryMarkers: new Map(),
  selectedDeliveryZoneId: null,
};

const elements = {
  cartClear: document.querySelector("#cart-clear"),
  cartCount: document.querySelector("#cart-count"),
  cartDialog: document.querySelector("#cart-dialog"),
  cartEmpty: document.querySelector("#cart-empty"),
  cartShare: document.querySelector("#cart-share"),
  cartItems: document.querySelector("#cart-items"),
  cartOpen: document.querySelector("#cart-open"),
  cartSubtotal: document.querySelector("#cart-subtotal"),
  cartSubtotalLabel: document.querySelector("#cart-subtotal-label"),
  cartDeliveryCost: document.querySelector("#cart-delivery-cost"),
  cartDeliveryNote: document.querySelector("#cart-delivery-note"),
  cartEstimatedTotal: document.querySelector("#cart-estimated-total"),
  cartDiscountRow: document.querySelector("#cart-discount-row"),
  cartDiscountAmount: document.querySelector("#cart-discount-amount"),
  cartCashback: document.querySelector("#cart-cashback"),
  cartCashbackAmount: document.querySelector("#cart-cashback-amount"),
  cartCashbackLabel: document.querySelector("#cart-cashback-label"),
  cartCashbackNote: document.querySelector("#cart-cashback-note"),
  catalogResultsLayout: document.querySelector("#catalog-results-layout"),
  categorySidebar: document.querySelector("#category-sidebar"),
  categorySidebarToggle: document.querySelector("#category-sidebar-toggle"),
  categorySubtabs: document.querySelector("#category-subtabs"),
  productProfile: document.querySelector("#product-profile"),
  categorySelect: document.querySelector("#product-category"),
  checkoutFeedback: document.querySelector("#checkout-feedback"),
  checkoutForm: document.querySelector("#checkout-form"),
  contactAddress: document.querySelector("#contact-address"),
  contactEmail: document.querySelector("#contact-email"),
  contactPhone: document.querySelector("#contact-phone"),
  contactWhatsapp: document.querySelector("#contact-whatsapp"),
  currentYear: document.querySelector("#current-year"),
  preferredDate: document.querySelector("#preferred-date"),
  deliveryEstimate: document.querySelector("#delivery-estimate"),
  deliveryDialog: document.querySelector("#delivery-dialog"),
  deliveryDialogZones: document.querySelector("#delivery-dialog-zones"),
  deliveryMap: document.querySelector("#delivery-map"),
  deliveryMapStatus: document.querySelector("#delivery-map-status"),
  deliveryNote: document.querySelector("#delivery-service-note"),
  deliveryOpen: document.querySelector("#delivery-open"),
  deliveryTown: document.querySelector("#delivery-town"),
  deliveryZones: document.querySelector("#delivery-zones"),
  deliveryDisclaimer: document.querySelector("#delivery-disclaimer"),
  emptyState: document.querySelector("#empty-state"),
  footerBusinessCopy: document.querySelector("#footer-business-copy"),
  hero: document.querySelector("#inizio"),
  heroAction: document.querySelector("#hero-action"),
  heroActionLabel: document.querySelector("#hero-action-label"),
  heroCaption: document.querySelector("#hero-caption"),
  heroDeliveryHighlight: document.querySelector("#hero-delivery-highlight"),
  heroDeliverySecondary: document.querySelector("#hero-delivery-secondary"),
  heroEyebrow: document.querySelector("#hero-eyebrow"),
  heroImage: document.querySelector("#hero-image"),
  heroIntro: document.querySelector("#hero-intro"),
  heroNext: document.querySelector("#hero-next"),
  heroPrevious: document.querySelector("#hero-previous"),
  heroSlideCount: document.querySelector("#hero-slide-count"),
  heroTitle: document.querySelector("#hero-title"),
  heroToggle: document.querySelector("#hero-toggle"),
  legalDetails: document.querySelector("#legal-details"),
  legalDetailsList: document.querySelector("#legal-details-list"),
  liveMessage: document.querySelector("#live-message"),
  menuToggle: document.querySelector("#menu-toggle"),
  navigation: document.querySelector("#primary-navigation"),
  orderSubmit: document.querySelector("#order-submit"),
  orderSubmitLabel: document.querySelector("#order-submit-label"),
  otherTown: document.querySelector("#other-town"),
  otherTownField: document.querySelector("#other-town-field"),
  productCount: document.querySelector("#product-count"),
  productGrid: document.querySelector("#product-grid"),
  productSearch: document.querySelector("#product-search"),
  productSort: document.querySelector("#product-sort"),
  productViewButtons: document.querySelectorAll("[data-product-view]"),
  productSheet: document.querySelector("#product-sheet"),
  productSheetBody: document.querySelector("#product-sheet-body"),
  productSheetAddAll: document.querySelector("#product-sheet-add-all"),
  productSheetOrderBar: document.querySelector("#product-sheet-order-bar"),
  productSheetOrderSummary: document.querySelector("#product-sheet-order-summary"),
  catalogShare: document.querySelector("#catalog-share"),
  catalogShare: document.querySelector("#catalog-share"),
  catalogShareStatus: document.querySelector("#catalog-share-status"),
  preferredTimeStart: document.querySelector("#preferred-time-start"),
  preferredTimeEnd: document.querySelector("#preferred-time-end"),
  promoDialog: document.querySelector("#promo-dialog"),
  promoOpen: document.querySelector("#promo-open"),
  promoOpenTop: document.querySelector("#promo-open-top"),
  quickMessageButtons: document.querySelectorAll("[data-quick-message-button]"),
  productDialog: document.querySelector("#product-dialog"),
  productDialogAdd: document.querySelector("#product-dialog-add"),
  productDialogCategory: document.querySelector("#product-dialog-category"),
  productDialogDescription: document.querySelector("#product-dialog-description"),
  productDialogDetail: document.querySelector("#product-dialog-detail"),
  productDialogImage: document.querySelector("#product-dialog-image"),
  productDialogCounter: document.querySelector("#product-dialog-counter"),
  productDialogNext: document.querySelector("#product-dialog-next"),
  productDialogPrevious: document.querySelector("#product-dialog-previous"),
  productDialogPrice: document.querySelector("#product-dialog-price"),
  productDialogThumbnails: document.querySelector("#product-dialog-thumbnails"),
  productDialogTitle: document.querySelector("#product-dialog-title"),
  productDialogUnit: document.querySelector("#product-dialog-unit"),
  productDialogUnitPrice: document.querySelector("#product-dialog-unit-price"),
  productDialogUnitPriceWrap: document.querySelector("#product-dialog-unit-price-wrap"),
  productDetail: document.querySelector("#product-detail"),
  productNotFound: document.querySelector("#product-not-found"),
  detailAdd: document.querySelector("#detail-add"),
  detailCategory: document.querySelector("#detail-category"),
  detailDescription: document.querySelector("#detail-description"),
  detailImage: document.querySelector("#detail-image"),
  detailImageCounter: document.querySelector("#detail-image-counter"),
  detailImageNext: document.querySelector("#detail-image-next"),
  detailImagePrevious: document.querySelector("#detail-image-previous"),
  detailSpecifications: document.querySelector("#detail-specifications"),
  detailSpecificationsSection: document.querySelector("#detail-specifications-section"),
  detailThumbnails: document.querySelector("#detail-thumbnails"),
  detailTitle: document.querySelector("#detail-title"),
  detailUnit: document.querySelector("#detail-unit"),
  detailPrice: document.querySelector("#detail-price"),
  detailUnitPrice: document.querySelector("#detail-unit-price"),
  detailUnitPriceWrap: document.querySelector("#detail-unit-price-wrap"),
  detailBreadcrumbTitle: document.querySelector("#detail-breadcrumb-title"),
  cartSummary: document.querySelector("#cart-summary"),
  recurringOrder: document.querySelector('[name="recurring-order"]'),
  recurringOptions: document.querySelector("#recurring-options"),
  recurringFrequency: document.querySelector("#recurring-frequency"),
  recurringDay: document.querySelector("#recurring-day"),
  recurringDayField: document.querySelector("#recurring-day-field"),
  recurringHint: document.querySelector("#recurring-hint"),
  recurringPriceLockNote: document.querySelector("#recurring-price-lock-note"),
  recurringDiscountFaq: document.querySelector("#recurring-discount-faq"),
  recurringPriceLockFaq: document.querySelector("#recurring-price-lock-faq"),
  recurringFrequencyFaq: document.querySelector("#recurring-frequency-faq"),
  zone1DeliveryFaq: document.querySelector("#zone-01-delivery-faq"),
  zone2DeliveryFaq: document.querySelector("#zone-02-delivery-faq"),
  zone3DeliveryFaq: document.querySelector("#zone-03-delivery-faq"),
};

let leafletPromise = null;

function readCart() {
  try {
    const stored = JSON.parse(localStorage.getItem(cartStorageKey) || "{}");
    if (!stored || typeof stored !== "object" || Array.isArray(stored)) return {};
    return Object.fromEntries(
      Object.entries(stored).filter(([, quantity]) => Number.isInteger(quantity) && quantity > 0),
    );
  } catch {
    return {};
  }
}

function saveCart() {
  try {
    localStorage.setItem(cartStorageKey, JSON.stringify(state.cart));
  } catch {
    showMessage("Il browser non ha potuto salvare il carrello su questo dispositivo.");
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character];
  });
}

function safeImageUrl(value) {
  if (typeof value !== "string" || !value.trim()) return fallbackImage;
  try {
    const url = new URL(value.trim(), window.location.href);
    if (url.origin === window.location.origin || url.protocol === "https:") return url.href;
  } catch {
    return fallbackImage;
  }
  return fallbackImage;
}

function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("it-IT");
}

function formatPrice(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? euro.format(amount) : euro.format(0);
}

function formatPercentage(value) {
  return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2 }).format(value);
}

function getRecurringDiscountPercent() {
  const value = Number(state.site.recurring_order?.discount_percent);
  return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0;
}

function priceInCents(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? Math.round(amount * 100) : 0;
}

function pricesIncludeVat() {
  return state.site.prices_include_vat !== false;
}

function configuredCategoryPath(path) {
  const categories = Array.isArray(state.site.categories) ? state.site.categories : [];
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

function productVatRate(product) {
  const categories = configuredCategoryPath(productCategories(product.category));
  for (let index = categories.length - 1; index >= 0; index -= 1) {
    const value = categories[index].vat_rate;
    if (value === null || value === undefined || (typeof value === "string" && !value.trim())) continue;
    const rate = Number(value);
    return Number.isFinite(rate) && rate >= 0 && rate <= 100 ? rate : null;
  }
  return null;
}

function productPriceInCents(product) {
  const price = priceInCents(product.price);
  if (pricesIncludeVat()) return price;
  const rate = productVatRate(product);
  return rate === null ? null : price + Math.round(price * rate / 100);
}

function recurringPriceInCents(price) {
  return Math.round(priceInCents(price) * (100 - getRecurringDiscountPercent()) / 100);
}

function productRecurringPriceInCents(product) {
  const price = productPriceInCents(product);
  return price === null ? null : Math.round(price * (100 - getRecurringDiscountPercent()) / 100);
}

function orderVatAmountCents(entries, recurring = false) {
  let total = 0;
  for (const { product, quantity } of entries) {
    const rate = productVatRate(product);
    const price = productPriceInCents(product);
    if (rate === null || price === null) return null;
    const grossPrice = recurring
      ? Math.round(price * (100 - getRecurringDiscountPercent()) / 100)
      : price;
    total += Math.round(grossPrice * rate / (100 + rate)) * quantity;
  }
  return total;
}

function formatProductPrice(product) {
  const price = productPriceInCents(product);
  return price === null ? "Aliquota IVA da configurare" : formatPrice(price / 100);
}

function recurringFrequencyOptions() {
  const configuredDays = state.site.recurring_order?.frequency_days;
  const legacyLabels = state.site.recurring_order?.frequency_labels || {};
  const seenDays = new Set();
  return Array.isArray(configuredDays)
    ? configuredDays.map((entry) => {
        const option = entry && typeof entry === "object" && !Array.isArray(entry) ? entry : null;
        const days = Number(option ? option.days : entry);
        const label = (option && option.label) || legacyLabels[`day_${days}`];
        return { days, label: typeof label === "string" ? label.trim() : "" };
      }).filter(({ days }) => {
        if (!Number.isInteger(days) || days <= 0 || seenDays.has(days)) return false;
        seenDays.add(days);
        return true;
      })
    : [];
}

function recurringFrequencyDays() {
  return recurringFrequencyOptions().map(({ days }) => days);
}

function formatRecurringFrequency(days) {
  const dayCount = Number(days);
  const option = recurringFrequencyOptions().find(({ days: configuredDays }) => configuredDays === dayCount);
  return option?.label || `Ogni ${dayCount} giorni`;
}

function formatRecurringFrequencyList(frequencies = recurringFrequencyDays()) {
  const labels = frequencies.map((days) => formatRecurringFrequency(days).replace(/^Ogni /, "ogni "));
  if (!labels.length) return "";
  const lastLabel = labels.pop();
  return labels.length ? `${labels.join(", ")} o ${lastLabel}` : lastLabel;
}

function techVoucherPercent(recurring = false) {
  const configuredPercent = recurring
    ? state.site.recurring_order?.tech_voucher_percent
    : state.site.tech_voucher?.percent;
  const value = Number(configuredPercent);
  const fallbackPercent = recurring ? 50 : 25;
  return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : fallbackPercent;
}

function techVoucherMaximumCents() {
  return optionalPriceInCents(state.site.tech_voucher?.maximum_amount) ?? 2500;
}

function techVoucherExampleOrderCents(recurring = false) {
  const percent = techVoucherPercent(recurring);
  const maximumCents = techVoucherMaximumCents();
  return percent > 0 && maximumCents > 0
    ? Math.ceil(maximumCents * 100 / percent)
    : null;
}

function techVoucherValidityDays(recurring = false) {
  const configuredDays = recurring
    ? state.site.recurring_order?.tech_voucher_validity_days
    : state.site.tech_voucher?.validity_days;
  const days = Number(configuredDays);
  return Number.isInteger(days) && days > 0 ? days : recurring ? 90 : 60;
}

function techVoucherValidityText(recurring = false) {
  const days = techVoucherValidityDays(recurring);
  return `${days} ${days === 1 ? "giorno" : "giorni"}`;
}

function techVoucherAmountCents(subtotalCents, recurring = false) {
  return Math.min(Math.round(subtotalCents * techVoucherPercent(recurring) / 100), techVoucherMaximumCents());
}

function configureTechVoucher() {
  const standardExampleOrderCents = techVoucherExampleOrderCents(false);
  const recurringExampleOrderCents = techVoucherExampleOrderCents(true);
  document.querySelectorAll("[data-tech-voucher-example]").forEach((element) => {
    element.hidden = standardExampleOrderCents === null || recurringExampleOrderCents === null;
  });
  document.querySelectorAll("[data-tech-voucher-standard-example-order]").forEach((element) => {
    if (standardExampleOrderCents !== null) element.textContent = formatPrice(standardExampleOrderCents / 100);
  });
  document.querySelectorAll("[data-tech-voucher-recurring-example-order]").forEach((element) => {
    if (recurringExampleOrderCents !== null) element.textContent = formatPrice(recurringExampleOrderCents / 100);
  });
  document.querySelectorAll("[data-tech-voucher-standard-percent]").forEach((element) => {
    element.textContent = `${formatPercentage(techVoucherPercent(false))}%`;
  });
  document.querySelectorAll("[data-tech-voucher-recurring-percent]").forEach((element) => {
    element.textContent = `${formatPercentage(techVoucherPercent(true))}%`;
  });
  document.querySelectorAll("[data-tech-voucher-maximum]").forEach((element) => {
    element.textContent = formatPrice(techVoucherMaximumCents() / 100);
  });
  document.querySelectorAll("[data-tech-voucher-validity]").forEach((element) => {
    element.textContent = techVoucherValidityText();
  });
  document.querySelectorAll("[data-tech-voucher-recurring-validity]").forEach((element) => {
    element.textContent = techVoucherValidityText(true);
  });
}

function configureRecurringOrder() {
  const config = state.site.recurring_order || {};
  const discount = getRecurringDiscountPercent();
  const configuredMonths = Number(config.price_lock_months);
  const priceLockMonths = Number.isInteger(configuredMonths) && configuredMonths > 0 ? configuredMonths : 12;
  const frequencies = recurringFrequencyDays();
  const previousFrequency = elements.recurringFrequency.value;
  const options = frequencies.map((days) => {
    const option = document.createElement("option");
    option.value = String(days);
    option.textContent = formatRecurringFrequency(days);
    return option;
  });

  elements.recurringFrequency.replaceChildren(...options);
  if (frequencies.includes(Number(previousFrequency))) {
    elements.recurringFrequency.value = previousFrequency;
  }
  elements.recurringHint.textContent = `${formatPercentage(discount)}% di sconto · prezzo bloccato per ${priceLockMonths} mesi`;
  elements.recurringPriceLockNote.textContent = `Prezzi bloccati per ${priceLockMonths} mesi.`;
  elements.recurringDayField.hidden = config.fixed_delivery_day === false;

  if (elements.recurringDiscountFaq) elements.recurringDiscountFaq.textContent = `${formatPercentage(discount)}%`;
  if (elements.recurringPriceLockFaq) elements.recurringPriceLockFaq.textContent = `${priceLockMonths} mesi`;
  const frequencyText = formatRecurringFrequencyList(frequencies);
  if (elements.recurringFrequencyFaq) elements.recurringFrequencyFaq.textContent = frequencyText;
  document.querySelectorAll("[data-recurring-discount-percent]").forEach((element) => {
    element.textContent = `${formatPercentage(discount)}%`;
  });
  document.querySelectorAll("[data-recurring-price-lock]").forEach((element) => {
    element.textContent = `${priceLockMonths} mesi`;
  });
  document.querySelectorAll("[data-recurring-frequency-days]").forEach((element) => {
    element.textContent = frequencyText;
  });
}

function quickMessageTemplateValues(message) {
  const maximumAmount = formatPrice(techVoucherMaximumCents() / 100);

  if (message === "tech") {
    return {
      standard_percent: `${formatPercentage(techVoucherPercent(false))}%`,
      recurring_percent: `${formatPercentage(techVoucherPercent(true))}%`,
      maximum_amount: maximumAmount,
      validity_days: techVoucherValidityText(false),
      recurring_validity_days: techVoucherValidityText(true),
      standard_example_amount: formatPrice((techVoucherExampleOrderCents(false) ?? 0) / 100),
      recurring_example_amount: formatPrice((techVoucherExampleOrderCents(true) ?? 0) / 100),
    };
  }

  const configuredMonths = Number(state.site.recurring_order?.price_lock_months);
  const priceLockMonths = Number.isInteger(configuredMonths) && configuredMonths > 0 ? configuredMonths : 12;
  return {
    discount_percent: `${formatPercentage(getRecurringDiscountPercent())}%`,
    price_lock_months: `${priceLockMonths} mesi`,
    frequency_days: formatRecurringFrequencyList(),
    tech_voucher_recurring_percent: `${formatPercentage(techVoucherPercent(true))}%`,
    recurring_validity_days: techVoucherValidityText(true),
    maximum_amount: maximumAmount,
  };
}

function quickMessageLinkUrl(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  try {
    const url = new URL(value.trim(), window.location.href);
    if (url.protocol === "https:" || url.origin === window.location.origin) return url.href;
  } catch {
    return "";
  }
  return "";
}

function renderQuickMessageCopy(element, message, field) {
  const template = state.site.quick_messages?.[message]?.[field];
  if (typeof template !== "string") return false;

  const values = quickMessageTemplateValues(message);
  const linkConfig = state.site.quick_messages?.tech || {};
  const fragment = document.createDocumentFragment();
  const placeholder = /\{([a-z][a-z0-9_]*)\}/gi;
  let previousIndex = 0;

  for (const match of template.matchAll(placeholder)) {
    const matchIndex = match.index ?? previousIndex;
    fragment.append(document.createTextNode(template.slice(previousIndex, matchIndex)));

    if (match[1] === "link") {
      const linkLabel = String(linkConfig.link_label || "");
      const linkUrl = quickMessageLinkUrl(linkConfig.link_url);
      if (linkUrl) {
        const link = document.createElement("a");
        link.href = linkUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = linkLabel;
        fragment.append(link);
      } else {
        fragment.append(document.createTextNode(linkLabel || match[0]));
      }
    } else {
      const value = values[match[1]];
      fragment.append(document.createTextNode(value === undefined ? match[0] : value));
    }

    previousIndex = matchIndex + match[0].length;
  }

  fragment.append(document.createTextNode(template.slice(previousIndex)));
  element.replaceChildren(fragment);
  return true;
}

function configureQuickMessages() {
  document.querySelectorAll("[data-quick-message-copy]").forEach((element) => {
    const [message, field] = element.dataset.quickMessageCopy.split(".");
    if (message && field) renderQuickMessageCopy(element, message, field);
  });
}

let quickMessageIndex = 0;

function renderQuickMessage(index) {
  const buttons = [...elements.quickMessageButtons];
  const slides = buttons[0]?.querySelectorAll("[data-quick-message-slide]");
  if (!slides?.length) return;

  quickMessageIndex = ((index % slides.length) + slides.length) % slides.length;
  const activeMessage = slides[quickMessageIndex].dataset.quickMessageSlide;
  buttons.forEach((button) => {
    button.dataset.activeQuickMessage = activeMessage;
    button.querySelectorAll("[data-quick-message-slide]").forEach((slide) => {
      slide.hidden = slide.dataset.quickMessageSlide !== activeMessage;
    });
  });
}

function setupQuickMessageRotation() {
  if (!elements.quickMessageButtons.length) return;
  renderQuickMessage(0);
  window.setInterval(() => {
    const isPaused = document.hidden
      || [...elements.quickMessageButtons].some((button) => button.matches(":hover, :focus-within"))
      || elements.promoDialog.open;
    if (!isPaused) renderQuickMessage(quickMessageIndex + 1);
  }, 8000);
}

function openQuickMessage(message) {
  const isRecurring = message === "recurring";
  const activeMessage = isRecurring ? "recurring" : "tech";
  const title = elements.promoDialog.querySelector("#promo-dialog-title");
  const eyebrow = elements.promoDialog.querySelector("#promo-dialog-eyebrow");
  if (title && !renderQuickMessageCopy(title, activeMessage, "title")) {
    title.textContent = isRecurring ? "Vantaggi dell'ordine ricorrente" : "Il Buono Tech del mese";
  }
  if (eyebrow && !renderQuickMessageCopy(eyebrow, activeMessage, "eyebrow")) {
    eyebrow.textContent = isRecurring ? "CONVENIENZA PER ORDINI B2B" : "PROMO PER ORDINI B2B";
  }
  elements.promoDialog.querySelectorAll("[data-quick-message-dialog]").forEach((panel) => {
    panel.hidden = panel.dataset.quickMessageDialog !== activeMessage;
  });
  elements.promoDialog.setAttribute(
    "aria-describedby",
    isRecurring ? "recurring-order-description recurring-order-terms" : "promo-dialog-description promo-dialog-terms",
  );
  elements.promoDialog.showModal();
}

function updateRecurringControls() {
  const enabled = Boolean(elements.recurringOrder.checked);
  const fixedDeliveryDay = state.site.recurring_order?.fixed_delivery_day !== false;
  elements.recurringOptions.hidden = !enabled;
  elements.recurringFrequency.required = enabled;
  elements.recurringDay.required = enabled && fixedDeliveryDay;
  renderCart();
}

function productImages(product) {
  const images = [product.image, ...(Array.isArray(product.images) ? product.images : [])];
  return [...new Set(images
    .map((image) => typeof image === "string" ? image.trim() : "")
    .filter(Boolean))];
}

function productCategories(category) {
  const values = Array.isArray(category) ? category : [category];
  return values
    .flatMap((value) => typeof value === "string" ? value.split(" / ") : [])
    .map((value) => value.trim())
    .filter(Boolean);
}

function productCategoryLabel(category) {
  const path = productCategories(category);
  return path[path.length - 1] || "Carta";
}

function productCategoryGroups() {
  const groups = new Map();

  const addPath = (path) => {
    if (!path.length || path[0] === "tutte") return;
    const parentValue = path[0];
    const parent = groups.get(parentValue) || { value: parentValue, label: parentValue, children: [] };
    const value = path.join(" / ");
    if (path.length > 1 && !parent.children.some((child) => child.value === value)) {
      parent.children.push({ value, label: path.slice(1).join(" / "), parentValue });
    }
    groups.set(parentValue, parent);
  };

  const addCategory = (category, parentPath = []) => {
    const name = typeof category === "string" ? category : category?.name;
    const path = [...parentPath, ...productCategories(name)];
    if (!path.length) return;
    addPath(path);
    if (Array.isArray(category?.children)) {
      category.children.forEach((child) => addCategory(child, path));
    }
  };

  const configuredCategories = Array.isArray(state.site.categories) ? state.site.categories : [];
  configuredCategories.forEach((category) => addCategory(category));

  return [...groups.values()];
}

function categoryFilterButton(category, pressed) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = category.label;
  button.dataset.category = category.value;
  button.setAttribute("aria-pressed", String(pressed));
  button.addEventListener("click", () => {
    state.category = pressed ? category.parentValue : category.value;
    renderCategoryFilters();
    syncCatalogUrl();
    renderProducts();
  });
  return button;
}

function renderCategoryFilters() {
  if (!elements.categorySelect || !elements.categorySubtabs) return;

  const categories = productCategoryGroups();
  const parentValue = productCategories(state.category)[0];
  const activeGroup = categories.find((category) => category.value === parentValue);
  const mainOptions = [
    { value: "tutte", label: "Tutte le categorie" },
    ...categories.map(({ value, label }) => ({ value, label })),
  ].map(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  });
  elements.categorySelect.replaceChildren(...mainOptions);
  elements.categorySelect.value = activeGroup ? activeGroup.value : "tutte";

  const childButtons = (activeGroup?.children || []).map((category) =>
    categoryFilterButton(category, state.category === category.value));
  const hasSubcategories = childButtons.length > 0;
  elements.categorySubtabs.hidden = !hasSubcategories;
  if (elements.categorySidebar) elements.categorySidebar.hidden = !hasSubcategories;
  elements.catalogResultsLayout?.classList.toggle("has-category-sidebar", hasSubcategories);
  elements.categorySubtabs.replaceChildren(...childButtons);

  const isCompactViewport = window.matchMedia("(max-width: 1160px)").matches;
  if (isCompactViewport && !state.categorySubcategoriesExpanded) {
    const selectedButton = elements.categorySubtabs.querySelector('button[aria-pressed="true"]');
    if (selectedButton) elements.categorySubtabs.prepend(selectedButton);
  }

  const subcategoryButtons = [...elements.categorySubtabs.querySelectorAll("button")];
  const firstButtonTop = subcategoryButtons[0]?.getBoundingClientRect().top ?? 0;
  const firstRowButtons = subcategoryButtons.filter((button) =>
    Math.abs(button.getBoundingClientRect().top - firstButtonTop) < 1);
  const subtabsTop = elements.categorySubtabs.getBoundingClientRect().top;
  const firstRowBottom = firstRowButtons.reduce(
    (bottom, button) => Math.max(bottom, button.getBoundingClientRect().bottom),
    subtabsTop,
  );
  const hasAdditionalRows = isCompactViewport && subcategoryButtons.some(
    (button) => button.getBoundingClientRect().top > firstButtonTop + 1,
  );
  const canToggle = hasSubcategories && hasAdditionalRows;
  const isExpanded = canToggle && state.categorySubcategoriesExpanded;

  if (canToggle) {
    const collapsedHeight = Math.ceil(firstRowBottom - subtabsTop);
    elements.categorySubtabs.style.setProperty("--category-subtabs-collapsed-height", `${collapsedHeight}px`);
  } else {
    elements.categorySubtabs.style.removeProperty("--category-subtabs-collapsed-height");
    state.categorySubcategoriesExpanded = false;
  }

  elements.categorySidebar?.classList.toggle("is-collapsed", canToggle && !isExpanded);
  if (elements.categorySidebarToggle) {
    elements.categorySidebarToggle.hidden = !canToggle;
    elements.categorySidebarToggle.setAttribute("aria-expanded", String(isExpanded));
    elements.categorySidebarToggle.setAttribute(
      "aria-label",
      isExpanded ? "Riduci le sottocategorie" : `Mostra tutte le ${childButtons.length} sottocategorie`,
    );
    elements.categorySidebarToggle.textContent = isExpanded ? "Riduci" : `Mostra tutte (${childButtons.length})`;
  }
}

function productUnitLabel(unit) {
  if (!unit || typeof unit !== "object" || Array.isArray(unit)) return "";

  const quantity = unit.quantity === null || unit.quantity === undefined || unit.quantity === ""
    ? ""
    : unitNumber.format(Number(unit.quantity));
  const measure = String(unit.measure || "").trim();
  const primary = quantity && measure ? `${quantity} ${measure}` : "";
  const details = String(unit.details || "").trim();
  return [primary, details].filter(Boolean).join(" · ");
}

function productNameWithFormat(product) {
  const name = String(product.name || "Prodotto").trim();
  const unitLabel = productUnitLabel(product.unit);
  const primaryFormat = unitLabel.split(" · ")[0].trim();
  if (!primaryFormat || name.toLowerCase().includes(primaryFormat.toLowerCase())) return name;
  return `${name} ${unitLabel}`;
}

function productPricePerUnit(product) {
  const unit = product.unit;
  const price = productPriceInCents(product);
  if (!unit || typeof unit !== "object" || Array.isArray(unit)) return null;

  const quantity = Number(unit.quantity);
  const label = String(unit.pricePer || "").trim();
  if (!label || !Number.isFinite(quantity) || quantity <= 0 || price === null) return null;
  return { amount: Math.round(price / quantity) / 100, label };
}

function productCard(product) {
  const id = escapeHtml(product.id);
  const name = String(product.name || "Prodotto");
  const productUrl = `prodotto.html?id=${encodeURIComponent(String(product.id || ""))}`;
  const images = productImages(product);
  const imageCount = images.length;
  const unitLabel = productUnitLabel(product.unit);
  const pricePerUnit = productPricePerUnit(product);
  const priceAvailable = productPriceInCents(product) !== null;
  return `
    <article class="product-card">
      <div class="product-card__visual">
        <a class="product-card__image-button" href="${escapeHtml(productUrl)}" data-open-product="${id}" aria-label="Apri anteprima di ${escapeHtml(name)}">
          <img src="${escapeHtml(safeImageUrl(images[0] || fallbackImage))}" alt="${escapeHtml(name)}" loading="lazy" decoding="async" />
        </a>
        <span class="product-card__category">${escapeHtml(productCategoryLabel(product.category))}</span>
        ${state.page === "home" && product.featured === true ? `<span class="product-card__featured">In evidenza</span>` : ""}
        ${imageCount > 1 ? `<span class="product-card__image-count">${imageCount} foto</span>` : ""}
      </div>
      <div class="product-card__content">
        <h3><a class="product-card__title" href="${escapeHtml(productUrl)}" data-open-product="${id}">${escapeHtml(name)}</a></h3>
        <p class="product-card__unit">
          <span class="product-card__meta-label">Formato</span>
          <span class="product-card__unit-value">${escapeHtml(unitLabel)}</span>
        </p>
        <p class="product-card__description">${escapeHtml(product.description || "")}</p>
        <div class="product-card__purchase">
          <div class="product-price-set product-card__price-set">
            <div class="product-price-set__item product-price-set__item--total">
              <strong class="product-price-set__value product-card__total-price">${escapeHtml(formatProductPrice(product))}</strong>
            </div>
            ${pricePerUnit === null ? "" : `
              <div class="product-price-set__item product-price-set__item--unit">
                <span class="product-price-set__label">Prezzo unitario</span>
                <strong class="product-price-set__value product-price-set__unit-value">${escapeHtml(formatPrice(pricePerUnit.amount))} / ${escapeHtml(pricePerUnit.label)}</strong>
              </div>
            `}
          </div>
          <button class="add-button" type="button" data-add-to-cart="${id}" aria-label="Aggiungi ${escapeHtml(name)} al carrello"${priceAvailable ? "" : " disabled"}>
            <span class="add-button__plus" aria-hidden="true">+</span><span>Aggiungi</span>
          </button>
        </div>
      </div>
    </article>
  `;
}

function productSheetRow(product) {
  const id = escapeHtml(product.id);
  const name = String(product.name || "Prodotto");
  const productUrl = `prodotto.html?id=${encodeURIComponent(String(product.id || ""))}`;
  const image = productImages(product)[0] || fallbackImage;
  const pricePerUnit = productPricePerUnit(product);
  const price = formatProductPrice(product);
  const quantity = normalizeSheetQuantity(state.sheetQuantities[product.id] || 0);
  return `
    <tr data-sheet-product-id="${id}">
      <td class="product-sheet__product" data-label="Articolo"><a href="${escapeHtml(productUrl)}" data-open-product="${id}"><img class="product-sheet__thumbnail" src="${escapeHtml(safeImageUrl(image))}" alt="" loading="lazy" decoding="async" /><span>${escapeHtml(name)}</span></a></td>
      <td class="product-sheet__format" data-label="Formato"><strong>${escapeHtml(productUnitLabel(product.unit) || "—")}</strong></td>
      <td class="product-sheet__category" data-label="Categoria" title="${escapeHtml(productCategories(product.category).join(", ") || "Carta")}">${escapeHtml(productCategoryLabel(product.category))}</td>
      <td class="product-sheet__price" data-label="Prezzo confezione">${escapeHtml(price)}</td>
      <td class="product-sheet__price" data-label="Prezzo unitario">${pricePerUnit === null ? "—" : `${escapeHtml(formatPrice(pricePerUnit.amount))} / ${escapeHtml(pricePerUnit.label)}`}</td>
      <td class="product-sheet__quantity-cell" data-label="Quantità">
        <div class="product-sheet__stepper">
          <button class="product-sheet__step" type="button" data-sheet-step="-1" aria-label="Riduci quantità di ${escapeHtml(name)}"${quantity === 0 ? " disabled" : ""}>−</button>
          <input class="product-sheet__quantity" type="number" min="0" max="999" step="1" value="${quantity}" inputmode="numeric" data-sheet-quantity aria-label="Quantità da aggiungere di ${escapeHtml(name)}" />
          <button class="product-sheet__step" type="button" data-sheet-step="1" aria-label="Aumenta quantità di ${escapeHtml(name)}"${quantity === 999 ? " disabled" : ""}>+</button>
        </div>
      </td>
    </tr>
  `;
}

function normalizeSheetQuantity(value) {
  const quantity = Number(value);
  return Number.isSafeInteger(quantity) ? Math.min(999, Math.max(0, quantity)) : 0;
}

function refreshProductSheetOrderBar() {
  const selectedProducts = Object.entries(state.sheetQuantities)
    .map(([id, value]) => ({
      product: state.products.find((item) => item.id === id && item.available !== false),
      quantity: normalizeSheetQuantity(value),
    }))
    .filter(({ product, quantity }) => product && quantity > 0);
  const maxQuantity = selectedProducts.reduce((maximum, entry) => Math.max(maximum, entry.quantity), 0);
  const totalQuantity = selectedProducts.reduce((sum, entry) => sum + entry.quantity, 0);
  const priceConfigurationMissing = selectedProducts.some(({ product }) => productPriceInCents(product) === null);
  const totalCents = selectedProducts.reduce(
    (sum, entry) => sum + (productPriceInCents(entry.product) ?? 0) * entry.quantity,
    0,
  );

  if (elements.productSheetOrderBar) {
    elements.productSheetOrderBar.hidden = state.page !== "catalog" || state.view !== "excel";
  }
  if (elements.productSheetOrderSummary) {
    const itemLabel = totalQuantity === 1 ? "articolo" : "articoli";
    elements.productSheetOrderSummary.textContent = priceConfigurationMissing
      ? `${totalQuantity} ${itemLabel} · Aliquote IVA da configurare`
      : `${totalQuantity} ${itemLabel} · ${formatPrice(totalCents / 100)}`;
  }
  if (elements.productSheetAddAll) {
    elements.productSheetAddAll.disabled = totalQuantity === 0 || priceConfigurationMissing;
    elements.productSheetAddAll.textContent = `Aggiungi al carrello (${totalQuantity})`;
    elements.productSheetAddAll.setAttribute("aria-label", `Aggiungi al carrello, ${totalQuantity} ${totalQuantity === 1 ? "articolo" : "articoli"}`);
  }
  elements.productSheetBody?.querySelectorAll("[data-sheet-quantity]").forEach((input) => {
    const quantity = normalizeSheetQuantity(input.value);
    const row = input.closest("tr");
    const decrease = row?.querySelector('[data-sheet-step="-1"]');
    const increase = row?.querySelector('[data-sheet-step="1"]');
    if (row) {
      row.toggleAttribute("data-sheet-selected", quantity > 0);
      if (quantity > 0) {
        const strength = maxQuantity <= 1 ? 58 : 18 + ((quantity - 1) / (maxQuantity - 1)) * 40;
        row.style.setProperty("--sheet-quantity-strength", `${strength}%`);
      } else {
        row.style.removeProperty("--sheet-quantity-strength");
      }
    }
    if (decrease) decrease.disabled = quantity === 0;
    if (increase) increase.disabled = quantity === 999;
  });
}

function renderProductDialogImage(index = 0) {
  if (!state.dialogProduct || state.dialogImages.length === 0) return;

  const imageCount = state.dialogImages.length;
  state.dialogImageIndex = ((index % imageCount) + imageCount) % imageCount;
  elements.productDialogImage.src = safeImageUrl(state.dialogImages[state.dialogImageIndex]);
  elements.productDialogImage.alt = `${state.dialogProduct.name}, foto ${state.dialogImageIndex + 1}`;
  elements.productDialogCounter.textContent = `${state.dialogImageIndex + 1} / ${imageCount}`;
  elements.productDialogCounter.hidden = imageCount < 2;
  elements.productDialogPrevious.hidden = imageCount < 2;
  elements.productDialogNext.hidden = imageCount < 2;
  elements.productDialogThumbnails.hidden = imageCount < 2;

  if (imageCount > 1) {
    elements.productDialogThumbnails.innerHTML = state.dialogImages.map((image, imageIndex) => `
      <button
        class="product-dialog__thumbnail${imageIndex === state.dialogImageIndex ? " is-active" : ""}"
        type="button"
        data-gallery-index="${imageIndex}"
        aria-label="Mostra foto ${imageIndex + 1} di ${escapeHtml(state.dialogProduct.name)}"
        aria-pressed="${imageIndex === state.dialogImageIndex}"
      >
        <img src="${escapeHtml(safeImageUrl(image))}" alt="" loading="lazy" decoding="async" />
      </button>
    `).join("");
  } else {
    elements.productDialogThumbnails.replaceChildren();
  }
}

function openProductDialog(productId) {
  const product = state.products.find((item) => item.id === productId && item.available !== false);
  if (!product || !elements.productDialog) return;

  state.dialogProduct = product;
  state.dialogImages = productImages(product);
  if (state.dialogImages.length === 0) state.dialogImages = [fallbackImage];
  elements.productDialogTitle.textContent = product.name || "Prodotto";
  elements.productDialogCategory.textContent = productCategoryLabel(product.category);
  elements.productDialogUnit.textContent = productUnitLabel(product.unit);
  elements.productDialogPrice.textContent = formatProductPrice(product);
  const pricePerUnit = productPricePerUnit(product);
  if (elements.productDialogUnitPriceWrap && elements.productDialogUnitPrice) {
    elements.productDialogUnitPriceWrap.hidden = pricePerUnit === null;
    elements.productDialogUnitPrice.textContent = pricePerUnit === null
      ? ""
      : `${formatPrice(pricePerUnit.amount)} / ${pricePerUnit.label}`;
  }
  elements.productDialogDescription.textContent = product.description || "";
  elements.productDialogDetail.href = `prodotto.html?id=${encodeURIComponent(String(product.id))}`;
  renderProductDialogImage();
  elements.productDialog.showModal();
}

function renderDetailImage(index = 0) {
  if (!state.detailProduct || state.detailImages.length === 0) return;

  const imageCount = state.detailImages.length;
  state.detailImageIndex = ((index % imageCount) + imageCount) % imageCount;
  elements.detailImage.src = safeImageUrl(state.detailImages[state.detailImageIndex]);
  elements.detailImage.alt = `${state.detailProduct.name}, foto ${state.detailImageIndex + 1}`;
  elements.detailImageCounter.textContent = `${state.detailImageIndex + 1} / ${imageCount}`;
  elements.detailImageCounter.hidden = imageCount < 2;
  elements.detailImagePrevious.hidden = imageCount < 2;
  elements.detailImageNext.hidden = imageCount < 2;
  elements.detailThumbnails.hidden = imageCount < 2;

  if (imageCount > 1) {
    elements.detailThumbnails.innerHTML = state.detailImages.map((image, imageIndex) => `
      <button
        class="product-detail__thumbnail${imageIndex === state.detailImageIndex ? " is-active" : ""}"
        type="button"
        data-detail-image-index="${imageIndex}"
        aria-label="Mostra foto ${imageIndex + 1} di ${escapeHtml(state.detailProduct.name)}"
        aria-pressed="${imageIndex === state.detailImageIndex}"
      >
        <img src="${escapeHtml(safeImageUrl(image))}" alt="" loading="lazy" decoding="async" />
      </button>
    `).join("");
  } else {
    elements.detailThumbnails.replaceChildren();
  }
}

function renderProductDetail() {
  if (!elements.productDetail) return;

  const requestedId = new URLSearchParams(window.location.search).get("id");
  const product = state.products.find((item) => item.id === requestedId && item.available !== false);
  if (!product) {
    elements.productDetail.hidden = true;
    elements.productNotFound.hidden = false;
    const brand = String(state.site.brand || "Cartaway").trim();
    updateSeoMetadata({
      title: `Prodotto non trovato | ${brand}`,
      description: `Il prodotto richiesto non è disponibile. Sfoglia il catalogo ${brand} o torna alla pagina iniziale.`,
      siteName: brand,
      pageType: "website",
      robots: "noindex,follow",
    });
    updateSeoStructuredData(null);
    return;
  }

  const brand = String(state.site.brand || "Cartaway").trim();
  const productName = String(product.name || "Prodotto").trim();
  const productNameForMetadata = productNameWithFormat(product);
  const productUnit = productUnitLabel(product.unit);
  state.detailProduct = product;
  state.detailImages = productImages(product);
  if (state.detailImages.length === 0) state.detailImages = [fallbackImage];
  elements.productDetail.hidden = false;
  elements.productNotFound.hidden = true;
  elements.detailTitle.textContent = productName;
  elements.detailCategory.textContent = productCategoryLabel(product.category);
  elements.detailUnit.textContent = productUnit;
  elements.detailPrice.textContent = formatProductPrice(product);
  const pricePerUnit = productPricePerUnit(product);
  if (elements.detailUnitPriceWrap && elements.detailUnitPrice) {
    elements.detailUnitPriceWrap.hidden = pricePerUnit === null;
    elements.detailUnitPrice.textContent = pricePerUnit === null
      ? ""
      : `${formatPrice(pricePerUnit.amount)} / ${pricePerUnit.label}`;
  }
  elements.detailDescription.textContent = product.description || "";
  elements.detailBreadcrumbTitle.textContent = productName;
  renderDetailImage();

  const specifications = Array.isArray(product.specifications)
    ? product.specifications.filter((item) => String(item.label || "").trim() && String(item.value || "").trim())
    : [];
  const specificationRows = specifications.flatMap((item) => {
    const label = document.createElement("dt");
    const value = document.createElement("dd");
    label.textContent = String(item.label).trim();
    value.textContent = String(item.value).trim();
    return [label, value];
  });
  elements.detailSpecifications.replaceChildren(...specificationRows);
  elements.detailSpecifications.hidden = specifications.length === 0;
  if (elements.detailSpecificationsSection) {
    elements.detailSpecificationsSection.hidden = specifications.length === 0;
  }

  const canonicalUrl = seoCanonicalUrl("product", product.id);
  const productImageUrls = productImages(product).map(safeImageUrl);
  const productDescription = String(product.description || "Scopri dettagli e caratteristiche del prodotto.").trim();
  const metaDescription = [
    `${productNameForMetadata}.`,
    productDescription,
    "Consegna a Montoro e nei comuni vicini.",
  ].join(" ");
  updateSeoMetadata({
    title: `${productNameForMetadata} | ${brand}`,
    description: normalizeSeoDescription(metaDescription),
    url: canonicalUrl,
    siteName: brand,
    pageType: "product",
    imageUrl: productImageUrls[0] || "",
    imageAlt: productNameForMetadata,
  });
  updateSeoStructuredData({
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Product",
        "@id": `${canonicalUrl}#product`,
        name: productNameForMetadata,
        url: canonicalUrl,
        ...(product.category ? { category: productCategories(product.category).join(", ") } : {}),
        ...(product.description ? { description: String(product.description) } : {}),
        ...(productImageUrls.length ? { image: productImageUrls } : {}),
        ...(specifications.length
          ? {
              additionalProperty: specifications.map((item) => ({
                "@type": "PropertyValue",
                name: String(item.label).trim(),
                value: String(item.value).trim(),
              })),
            }
          : {}),
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Catalogo", item: `${canonicalSiteOrigin}/` },
          { "@type": "ListItem", position: 2, name: productName, item: canonicalUrl },
        ],
      },
    ],
  });
}

function siteProfiles() {
  const profiles = Array.isArray(state.site.profiles) ? state.site.profiles : [];
  return profiles
    .filter((profile) => profile && typeof profile.value === "string" && profile.value.trim()
      && typeof profile.label === "string" && profile.label.trim())
    .map((profile) => ({ value: profile.value.trim(), label: profile.label.trim() }));
}

function renderProfileFilter() {
  if (!elements.productProfile) return;

  const options = [
    { value: "tutte", label: "Tutte le attività" },
    ...siteProfiles(),
  ].map(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  });
  elements.productProfile.replaceChildren(...options);
  elements.productProfile.value = options.some((option) => option.value === state.profile)
    ? state.profile
    : "tutte";
}

function restoreCatalogStateFromUrl() {
  if (state.page !== "catalog") return;

  const params = new URLSearchParams(window.location.search);
  state.sharedOrder = params.get("order");
  state.sharedSheet = params.get("sheet");
  state.openSharedCart = params.get("openCart") === "1";
  const categoryValues = new Set(productCategoryGroups().flatMap((category) => [
    category.value,
    ...category.children.map((child) => child.value),
  ]));
  categoryValues.add("tutte");
  const requestedCategory = params.get("category");
  state.category = categoryValues.has(requestedCategory) ? requestedCategory : "tutte";
  state.categorySubcategoriesExpanded = state.category.includes(" / ");

  const profileValues = new Set(siteProfiles().map(({ value }) => value));
  const requestedProfile = params.get("profilo");
  state.profile = profileValues.has(requestedProfile) ? requestedProfile : "tutte";
  if (elements.productProfile) elements.productProfile.value = state.profile;

  const requestedSearch = params.get("q");
  state.search = requestedSearch || "";

  const sortValues = new Set(
    elements.productSort ? [...elements.productSort.options].map((option) => option.value) : ["featured"],
  );
  const requestedSort = params.get("sort");
  state.sort = sortValues.has(requestedSort) ? requestedSort : "featured";

  const requestedView = params.get("view");
  state.view = ["grid", "list", "excel"].includes(requestedView) ? requestedView : "grid";

  if (elements.productSearch) elements.productSearch.value = state.search;
  if (elements.productSort) elements.productSort.value = state.sort;
  document.body.classList.toggle("excel-view-active", state.view === "excel");
  renderCategoryFilters();
}

function syncCatalogUrl() {
  if (state.page !== "catalog") return;

  const url = new URL(window.location.href);
  ["category", "profilo", "q", "sort", "view"].forEach((key) => url.searchParams.delete(key));
  if (state.category !== "tutte") url.searchParams.set("category", state.category);
  if (state.profile !== "tutte") url.searchParams.set("profilo", state.profile);
  if (state.search.trim()) url.searchParams.set("q", state.search.trim());
  if (state.sort !== "featured") url.searchParams.set("sort", state.sort);
  if (state.view !== "grid") url.searchParams.set("view", state.view);
  window.history.replaceState(window.history.state, "", url);
  if (elements.catalogShareStatus) elements.catalogShareStatus.textContent = "";
}

function parseSharedOrder(serializedOrder) {
  if (serializedOrder === null) return null;

  let entries;
  try {
    entries = JSON.parse(serializedOrder);
  } catch {
    return null;
  }
  if (!Array.isArray(entries)) return null;

  const availableProductIds = new Set(
    state.products
      .filter((product) => product.available !== false)
      .map((product) => String(product.id)),
  );
  const sharedCart = {};
  entries.forEach((entry) => {
    if (!Array.isArray(entry) || entry.length !== 2) return;
    const [productId, quantity] = entry;
    if (
      typeof productId !== "string"
      || !availableProductIds.has(productId)
      || !Number.isSafeInteger(quantity)
      || quantity < 1
    ) return;
    sharedCart[productId] = quantity;
  });
  return sharedCart;
}

function buildCartShareUrl(items) {
  const shareUrl = new URL("/", window.location.href);
  shareUrl.search = "";
  shareUrl.hash = "";
  shareUrl.searchParams.set(
    "order",
    JSON.stringify(items.map(({ product, quantity }) => [product.id, quantity])),
  );
  shareUrl.searchParams.set("openCart", "1");
  return shareUrl;
}

function parseSharedSheet(serializedSheet) {
  if (serializedSheet === null) return {};

  let entries;
  try {
    entries = JSON.parse(serializedSheet);
  } catch {
    return {};
  }
  if (!Array.isArray(entries)) return {};

  const availableProductIds = new Set(
    state.products
      .filter((product) => product.available !== false)
      .map((product) => String(product.id)),
  );
  const sheetQuantities = {};
  entries.forEach((entry) => {
    if (!Array.isArray(entry) || entry.length !== 2) return;
    const [productId, quantity] = entry;
    if (
      typeof productId !== "string"
      || !availableProductIds.has(productId)
      || !Number.isSafeInteger(quantity)
      || quantity < 1
      || quantity > 999
    ) return;
    sheetQuantities[productId] = quantity;
  });
  return sheetQuantities;
}

function sortSheetColumn(column) {
  const ascendingSort = `${column}-asc`;
  const descendingSort = `${column}-desc`;
  state.sort = state.sort === ascendingSort ? descendingSort : ascendingSort;
  if (elements.productSort) elements.productSort.value = state.sort;
  syncCatalogUrl();
  renderProducts();
}

function renderProducts() {
  if (!elements.productGrid) return;

  const excelView = state.view === "excel";
  document.body.classList.toggle("excel-view-active", state.page === "catalog" && excelView);
  elements.productGrid.hidden = excelView;
  if (elements.productSheet) elements.productSheet.hidden = !excelView;
  elements.productGrid.classList.toggle("product-grid--list", state.view === "list");
  elements.productViewButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.productView === state.view));
  });

  let visibleProducts = state.products.filter((product) => product.available !== false);
  const selectedCategoryPath = productCategories(state.category);
  if (state.page !== "home") {
    visibleProducts = visibleProducts
      .filter((product) => {
        const categories = productCategories(product.category);
        return state.category === "tutte"
          || selectedCategoryPath.every((segment, index) => categories[index] === segment);
      })
  }

  if (state.profile !== "tutte") {
    visibleProducts = visibleProducts.filter((product) =>
      Array.isArray(product.profiles) && product.profiles.includes(state.profile));
  }

  const normalizedSearch = normalizeText(state.search.trim());
  visibleProducts = visibleProducts.filter((product) => {
    const searchable = normalizeText([product.name, ...productCategories(product.category), productUnitLabel(product.unit), product.description].join(" "));
    return searchable.includes(normalizedSearch);
  });

  if (state.sort === "unit-price-asc" || state.sort === "unit-price-desc") {
    const direction = state.sort === "unit-price-asc" ? 1 : -1;
    visibleProducts.sort((first, second) => {
      const firstPrice = productPricePerUnit(first)?.amount;
      const secondPrice = productPricePerUnit(second)?.amount;
      if (firstPrice === undefined) return secondPrice === undefined ? 0 : 1;
      if (secondPrice === undefined) return -1;
      return (firstPrice - secondPrice) * direction;
    });
  } else if (state.sort === "price-asc") {
    visibleProducts.sort((first, second) => (productPriceInCents(first) ?? Infinity) - (productPriceInCents(second) ?? Infinity));
  } else if (state.sort === "price-desc") {
    visibleProducts.sort((first, second) => (productPriceInCents(second) ?? -Infinity) - (productPriceInCents(first) ?? -Infinity));
  } else {
    visibleProducts.sort((first, second) => Number(second.featured === true) - Number(first.featured === true));
  }

  elements.productSheet?.querySelectorAll("[data-sheet-sort-header]").forEach((header) => {
    const column = header.dataset.sheetSortHeader;
    const ascending = state.sort === `${column}-asc`;
    const descending = state.sort === `${column}-desc`;
    header.setAttribute("aria-sort", ascending ? "ascending" : descending ? "descending" : "none");
    const indicator = header.querySelector(".product-sheet__sort-indicator");
    if (indicator) indicator.textContent = ascending ? "↑" : descending ? "↓" : "↕";
  });

  if (elements.productSheetAddAll) elements.productSheetAddAll.disabled = visibleProducts.length === 0;
  if (elements.productCount) {
    elements.productCount.textContent = `${visibleProducts.length} ${visibleProducts.length === 1 ? "prodotto" : "prodotti"}`;
  }
  if (excelView) {
    elements.productGrid.replaceChildren();
    if (elements.productSheetBody) elements.productSheetBody.innerHTML = visibleProducts.map(productSheetRow).join("");
  } else {
    elements.productGrid.innerHTML = visibleProducts.map(productCard).join("");
    if (elements.productSheetBody) elements.productSheetBody.replaceChildren();
  }
  if (elements.emptyState) elements.emptyState.hidden = visibleProducts.length > 0;
  refreshProductSheetOrderBar();
}

function cartEntries() {
  return Object.entries(state.cart)
    .map(([id, quantity]) => ({
      product: state.products.find((item) => item.id === id),
      quantity,
    }))
    .filter(({ product }) => product && product.available !== false);
}

function renderCart() {
  const entries = cartEntries();
  const quantity = entries.reduce((total, entry) => total + entry.quantity, 0);
  const recurring = elements.recurringOrder.checked;
  const discountPercent = getRecurringDiscountPercent();
  const priceConfigurationMissing = entries.some(({ product }) => productPriceInCents(product) === null);
  const fullSubtotalCents = entries.reduce(
    (total, entry) => total + (productPriceInCents(entry.product) ?? 0) * entry.quantity,
    0,
  );
  const subtotalCents = entries.reduce(
    (total, entry) => {
      const price = recurring ? productRecurringPriceInCents(entry.product) : productPriceInCents(entry.product);
      return total + (price ?? 0) * entry.quantity;
    },
    0,
  );
  const savingsCents = fullSubtotalCents - subtotalCents;
  const selectedTown = elements.deliveryTown.value === "altro"
    ? elements.otherTown.value.trim()
    : elements.deliveryTown.value;
  const deliveryZone = findDeliveryZoneForTown(selectedTown);
  const deliveryQuote = getDeliveryQuote(deliveryZone, subtotalCents, fullSubtotalCents);
  const minimumReached = !deliveryZone || deliveryQuote.minimumOrderCents === null || subtotalCents >= deliveryQuote.minimumOrderCents;

  elements.cartCount.textContent = String(quantity);
  elements.cartOpen.setAttribute("aria-label", `Apri carrello, ${quantity} ${quantity === 1 ? "articolo" : "articoli"}`);
  if (elements.cartClear) elements.cartClear.disabled = entries.length === 0;
  if (elements.cartShare) elements.cartShare.disabled = entries.length === 0;
  elements.cartItems.innerHTML = entries.map(({ product, quantity: itemQuantity }) => {
    const id = escapeHtml(product.id);
    const name = String(product.name || "Prodotto");
    const fullUnitPriceCents = productPriceInCents(product);
    const unitPriceCents = recurring ? productRecurringPriceInCents(product) : fullUnitPriceCents;
    const unitPrice = unitPriceCents === null
      ? "Aliquota IVA da configurare"
      : recurring && discountPercent > 0
        ? `<del>${escapeHtml(formatPrice(fullUnitPriceCents / 100))}</del> <strong>${escapeHtml(formatPrice(unitPriceCents / 100))}</strong>`
        : escapeHtml(formatPrice(unitPriceCents / 100));
    const pricePerUnit = productPricePerUnit(product);
    const comparableUnitPrice = pricePerUnit === null || unitPriceCents === null
      ? ""
      : `<p class="cart-item__unit-price">Prezzo unitario: ${escapeHtml(formatPrice(unitPriceCents / 100 / Number(product.unit.quantity)))} / ${escapeHtml(pricePerUnit.label)}</p>`;
    return `
      <article class="cart-item">
        <img class="cart-item__image" src="${escapeHtml(safeImageUrl(product.image))}" alt="" loading="lazy" />
        <div class="cart-item__details">
          <h3>${escapeHtml(name)}</h3>
          <p>${escapeHtml(productUnitLabel(product.unit))} · ${unitPrice}</p>
          ${comparableUnitPrice}
          <div class="quantity-control" role="group" aria-label="Quantità di ${escapeHtml(name)}">
            <button type="button" data-cart-change="-1" data-product-id="${id}" aria-label="Riduci ${escapeHtml(name)} di uno">−</button>
            <input class="quantity-control__input" type="number" min="1" step="1" inputmode="numeric" value="${itemQuantity}" data-cart-quantity="true" data-product-id="${id}" aria-label="Quantità di ${escapeHtml(name)}" />
            <button type="button" data-cart-change="1" data-product-id="${id}" aria-label="Aumenta ${escapeHtml(name)} di uno">+</button>
          </div>
        </div>
        <strong class="cart-item__amount">${escapeHtml(unitPriceCents === null ? "Aliquota IVA da configurare" : formatPrice(unitPriceCents * itemQuantity / 100))}</strong>
      </article>
    `;
  }).join("");

  elements.cartEmpty.hidden = entries.length > 0;
  elements.cartSummary.hidden = entries.length === 0;
  elements.checkoutForm.hidden = entries.length === 0;
  elements.orderSubmit.disabled = state.orderSubmitting || entries.length === 0 || !minimumReached || priceConfigurationMissing;
  elements.orderSubmit.setAttribute("aria-busy", String(state.orderSubmitting));
  elements.cartSubtotalLabel.textContent = recurring && discountPercent > 0 ? "Subtotale scontato" : "Subtotale articoli";
  elements.cartSubtotal.textContent = priceConfigurationMissing ? "Aliquote IVA da configurare" : formatPrice(subtotalCents / 100);
  elements.cartDeliveryCost.textContent = deliveryQuote.label;
  elements.cartDeliveryCost.dataset.deliveryState = deliveryQuote.state;
  elements.cartDeliveryNote.textContent = deliveryQuote.note;
  elements.cartEstimatedTotal.textContent = priceConfigurationMissing
    ? "Configura le aliquote IVA"
    : deliveryQuote.costCents === null
      ? minimumReached ? "Da confermare" : "Minimo non raggiunto"
      : formatPrice((subtotalCents + deliveryQuote.costCents) / 100);
  elements.cartDiscountRow.hidden = !recurring || savingsCents <= 0;
  elements.cartDiscountAmount.textContent = `−${formatPrice(savingsCents / 100)}`;
  elements.cartCashbackAmount.textContent = priceConfigurationMissing
    ? "Da configurare"
    : formatPrice(techVoucherAmountCents(subtotalCents, recurring) / 100);
  if (elements.cartCashbackLabel) {
    elements.cartCashbackLabel.textContent = recurring
      ? "Buono Tech stimato per un ordine ricorrente, se è il primo del mese"
      : "Buono Tech stimato per un ordine singolo, se è il primo del mese";
  }
  if (elements.cartCashbackNote) {
    const voucherValidity = recurring
      ? `valido ${techVoucherValidityText(true)} dalla consegna grazie all'ordine ricorrente`
      : `valido ${techVoucherValidityText()} dalla consegna`;
    elements.cartCashbackNote.textContent = `Stima pari al ${formatPercentage(techVoucherPercent(recurring))}% della spesa, fino a ${formatPrice(techVoucherMaximumCents() / 100)}, senza minimo. Un buono per cliente al mese, ${voucherValidity} e per un solo intervento. Non convertibile in denaro né cumulabile con altri buoni; idoneità da verificare con l'attività.`;
  }
  elements.cartCashback.hidden = entries.length === 0;

  if (!selectedTown) {
    elements.deliveryEstimate.textContent = "Seleziona il comune per stimare consegna e costo.";
  } else if (!deliveryZone) {
    elements.deliveryEstimate.textContent = "Verifichiamo copertura e costo per questo comune prima di confermare.";
  } else {
    const timing = String(deliveryZone.delivery_time || "").trim();
    elements.deliveryEstimate.textContent = `${selectedTown}: ${timing ? `${timing}. ` : ""}${deliveryQuote.note}`;
  }
}

function showMessage(message) {
  elements.liveMessage.textContent = message;
  elements.liveMessage.classList.add("is-visible");
  window.clearTimeout(showMessage.timer);
  showMessage.timer = window.setTimeout(() => {
    elements.liveMessage.classList.remove("is-visible");
  }, 2600);
}

function clearCheckoutFeedback() {
  elements.checkoutFeedback.hidden = true;
  elements.checkoutFeedback.textContent = "";
  elements.checkoutFeedback.classList.remove("checkout-feedback--success", "checkout-feedback--error");
}

function showCheckoutFeedback(message, type) {
  elements.checkoutFeedback.textContent = message;
  elements.checkoutFeedback.classList.remove("checkout-feedback--success", "checkout-feedback--error");
  elements.checkoutFeedback.classList.add(`checkout-feedback--${type}`);
  elements.checkoutFeedback.hidden = false;
}

function addToCart(productId) {
  const product = state.products.find((item) => item.id === productId && item.available !== false);
  if (!product) return;
  if (productPriceInCents(product) === null) {
    showMessage("Configura l'aliquota IVA della categoria prima di aggiungere questo prodotto.");
    return;
  }
  clearCheckoutFeedback();
  state.cart[productId] = (state.cart[productId] || 0) + 1;
  saveCart();
  renderCart();
  showMessage(`${product.name} aggiunto al carrello.`);
}

function setQuantity(productId, quantity) {
  if (!Number.isSafeInteger(quantity) || quantity < 0) return;
  if (quantity === 0) {
    delete state.cart[productId];
  } else {
    state.cart[productId] = quantity;
  }
  saveCart();
  renderCart();
}

function addSelectedProductsToCart() {
  const selectedProducts = Object.entries(state.sheetQuantities)
    .map(([id, value]) => ({
      product: state.products.find((item) => item.id === id && item.available !== false),
      quantity: normalizeSheetQuantity(value),
    }))
    .filter(({ product, quantity }) => product && quantity > 0);
  if (selectedProducts.some(({ product }) => productPriceInCents(product) === null)) {
    showMessage("Configura le aliquote IVA delle categorie prima di aggiungere i prodotti selezionati.");
    return;
  }
  if (selectedProducts.length === 0) {
    showMessage("Seleziona almeno una quantità da aggiungere.");
    return;
  }

  let unitCount = 0;
  selectedProducts.forEach(({ product, quantity }) => {
    state.cart[product.id] = (state.cart[product.id] || 0) + quantity;
    state.sheetQuantities[product.id] = 0;
    unitCount += quantity;
  });

  clearCheckoutFeedback();
  saveCart();
  renderCart();
  elements.productSheetBody?.querySelectorAll("[data-sheet-quantity]").forEach((input) => {
    input.value = "0";
  });
  refreshProductSheetOrderBar();
  showMessage(`${unitCount} articoli aggiunti al carrello.`);
}

function changeQuantity(productId, delta) {
  setQuantity(productId, (state.cart[productId] || 0) + delta);
}

function buildWhatsappUrl(message) {
  const number = String(state.site.whatsapp || "").replace(/\D/g, "");
  if (number.length < 8) return "";
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}

const canonicalSiteOrigin = "https://cartaway.it";

function seoCanonicalUrl(page = state.page, productId = "") {
  const pathname = page === "catalog"
    ? "/"
    : page === "help"
      ? "/primi-passi.html"
      : page === "product"
        ? "/prodotto.html"
        : "/";
  const url = new URL(pathname, canonicalSiteOrigin);
  if (page === "product" && productId) url.searchParams.set("id", String(productId));
  return url.href;
}

function setSeoMeta(attribute, key, value) {
  let meta = document.head.querySelector(`meta[${attribute}="${key}"]`);
  if (!value) {
    meta?.remove();
    return;
  }
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute(attribute, key);
    document.head.append(meta);
  }
  meta.setAttribute("content", String(value));
}

function normalizeSeoDescription(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= 160) return text;
  const shortened = text.slice(0, 157);
  const lastSpace = shortened.lastIndexOf(" ");
  return `${shortened.slice(0, lastSpace > 0 ? lastSpace : shortened.length).trim()}...`;
}

function updateSeoMetadata({ title, description, url, siteName, pageType, imageUrl = "", imageAlt = "", robots = "max-image-preview:large" }) {
  document.title = title;
  setSeoMeta("name", "description", normalizeSeoDescription(description));
  setSeoMeta("name", "robots", robots);
  setSeoMeta("property", "og:title", title);
  setSeoMeta("property", "og:description", normalizeSeoDescription(description));
  setSeoMeta("property", "og:type", pageType);
  setSeoMeta("property", "og:locale", "it_IT");
  setSeoMeta("property", "og:site_name", siteName);
  setSeoMeta("property", "og:url", url);
  setSeoMeta("property", "og:image", imageUrl);
  setSeoMeta("property", "og:image:alt", imageAlt);
  setSeoMeta("name", "twitter:card", imageUrl ? "summary_large_image" : "summary");
  setSeoMeta("name", "twitter:title", title);
  setSeoMeta("name", "twitter:description", normalizeSeoDescription(description));
  setSeoMeta("name", "twitter:image", imageUrl);
  setSeoMeta("name", "twitter:image:alt", imageAlt);

  let canonical = document.head.querySelector('link[rel="canonical"]');
  if (!url) {
    canonical?.remove();
    return;
  }
  if (!canonical) {
    canonical = document.createElement("link");
    canonical.rel = "canonical";
    document.head.append(canonical);
  }
  canonical.href = url;
}

function updateSeoStructuredData(data) {
  let script = document.head.querySelector("#seo-structured-data");
  if (!data) {
    script?.remove();
    return;
  }
  if (!script) {
    script = document.createElement("script");
    script.id = "seo-structured-data";
    script.type = "application/ld+json";
    document.head.append(script);
  }
  script.textContent = JSON.stringify(data).replace(/</g, "\\u003c");
}

function catalogStructuredData(title, description, url) {
  const products = state.products.filter((product) => product.available !== false);
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: title,
    description,
    url,
    inLanguage: "it-IT",
    mainEntity: {
      "@type": "ItemList",
      itemListOrder: "https://schema.org/ItemListUnordered",
      numberOfItems: products.length,
      itemListElement: products.map((product, index) => {
        const item = {
          "@type": "Product",
          name: String(product.name || "Prodotto"),
          url: seoCanonicalUrl("product", product.id),
        };
        const images = productImages(product).map(safeImageUrl);
        if (images.length) item.image = images;
        if (product.description) item.description = String(product.description);
        if (product.category) item.category = productCategories(product.category).join(" / ");
        return { "@type": "ListItem", position: index + 1, item };
      }),
    },
  };
}

function renderSiteDetails() {
  const brand = String(state.site.brand || "Cartaway").trim();
  const categories = Array.isArray(state.site.categories) ? state.site.categories : [];
  const allVatRatesConfigured = categories.length > 0
    && state.products.length > 0
    && state.products.every((product) => productVatRate(product) !== null);
  const vatStatus = pricesIncludeVat()
    ? "IVA inclusa"
    : allVatRatesConfigured
      ? "IVA aggiunta in base alla categoria"
      : "IVA esclusa · aliquote da configurare";
  document.querySelectorAll("[data-vat-status]").forEach((element) => {
    element.textContent = vatStatus;
  });
  document.querySelectorAll("[data-brand]").forEach((element) => {
    element.textContent = brand;
  });
  if (state.page === "cart") {
    if (elements.currentYear) elements.currentYear.textContent = String(new Date().getFullYear());
    renderDeliveryInfo();
    return;
  }
  if (state.page !== "product") {
    const isCatalog = state.page === "catalog";
    const isHelp = state.page === "help";
    const title = isCatalog
      ? `Catalogo carta per la casa, il lavoro e l'ufficio a Montoro | ${brand}`
      : isHelp
        ? `Come ordinare da ${brand} | Consegna a Montoro`
        : `${brand} | Carta per la casa, la cucina, il lavoro e l'ufficio a Montoro`;
    const description = isCatalog
      ? `Sfoglia il catalogo ${brand}: carta igienica, rotoli cucina, carta A4 e prodotti di carta per la casa, il lavoro e l'ufficio, con consegna a Montoro e nei comuni vicini.`
      : isHelp
        ? `Guida per ordinare da ${brand}: come inviare una richiesta, costi e zone di consegna a Montoro e nei comuni vicini.`
        : `Carta igienica, rotoli cucina e carta A4 per la casa, il lavoro e l'ufficio. ${brand} consegna a Montoro e nei comuni vicini, con tempi da concordare.`;
    const url = seoCanonicalUrl();
    updateSeoMetadata({ title, description, url, siteName: brand, pageType: "website" });
    updateSeoStructuredData(isCatalog
      ? catalogStructuredData(title, description, url)
      : isHelp
        ? {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "@id": `${url}#howto`,
            url,
            name: title,
            description,
            inLanguage: "it-IT",
            step: [
              {
                "@type": "HowToStep",
                position: 1,
                name: "Scegli i prodotti",
                text: "Aggiungi al carrello carta e prodotti dal catalogo.",
              },
              {
                "@type": "HowToStep",
                position: 2,
                name: "Invia la richiesta",
                text: "Inserisci i dati e ricevi via email il riepilogo della richiesta.",
              },
              {
                "@type": "HowToStep",
                position: 3,
                name: "Conferma i dettagli",
                text: "Cartaway verifica disponibilità, consegna e pagamento con te.",
              },
            ],
          }
        : {
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "Organization",
                "@id": `${canonicalSiteOrigin}/#organization`,
                name: brand,
                url: `${canonicalSiteOrigin}/`,
              },
              {
                "@type": "WebSite",
                "@id": `${canonicalSiteOrigin}/#website`,
                url: `${canonicalSiteOrigin}/`,
                name: brand,
                inLanguage: "it-IT",
                publisher: { "@id": `${canonicalSiteOrigin}/#organization` },
              },
            ],
          });
  }

  const email = String(state.site.email || "").trim();
  if (email) {
    elements.contactEmail.href = `mailto:${email}`;
    elements.contactEmail.textContent = email;
  } else {
    elements.contactEmail.hidden = true;
  }

  const phone = String(state.site.phone || "").trim();
  if (phone) {
    elements.contactPhone.href = `tel:${phone.replace(/[^\d+]/g, "")}`;
    elements.contactPhone.textContent = phone;
  } else {
    elements.contactPhone.hidden = true;
  }

  const whatsapp = buildWhatsappUrl(`Buongiorno ${brand}, vorrei informazioni su un ordine.`);
  if (whatsapp) {
    elements.contactWhatsapp.href = whatsapp;
  } else {
    elements.contactWhatsapp.hidden = true;
  }

  const address = String(state.site.address || "").trim();
  if (address) {
    elements.contactAddress.textContent = address;
  } else {
    elements.contactAddress.hidden = true;
  }

  const businessLines = [state.site.services, state.site.service_note]
    .map((line) => String(line || "").trim())
    .filter(Boolean);
  elements.footerBusinessCopy.textContent = businessLines.join(". ");
  elements.currentYear.textContent = String(new Date().getFullYear());
  renderDeliveryInfo();

  const legal = state.site.legal || {};
  const legalFields = [
    ["Titolare", legal.holder],
    ["Forma giuridica", legal.legal_form],
    ["Sede legale", legal.registered_office],
    ["Partita IVA", legal.vat_number],
    ["REA", legal.rea],
  ];
  const entries = legalFields
    .filter(([, value]) => String(value || "").trim())
    .map(([label, value]) => {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = String(value).trim();
      row.append(term, description);
      return row;
    });
  elements.legalDetailsList.replaceChildren(...entries);
  elements.legalDetails.hidden = entries.length === 0;
}

function optionalPriceInCents(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0 ? Math.round(amount * 100) : null;
}

function findDeliveryZoneForTown(town) {
  const normalizedTown = normalizeText(town);
  if (!normalizedTown) return null;
  return getDeliveryZones().find((zone) =>
    zone.locations.some((location) => normalizeText(location.name) === normalizedTown),
  ) || null;
}

function deliveryPolicyDescription(zone) {
  const minimumOrderCents = optionalPriceInCents(zone.minimum_order_amount);
  const freeMinimumCents = optionalPriceInCents(zone.free_delivery_minimum);
  const feeCents = optionalPriceInCents(zone.delivery_fee);

  if (zone.delivery_policy === "free") {
    if (minimumOrderCents === 0) return "Consegna gratuita, senza importo minimo d'ordine.";
    if (minimumOrderCents !== null) return `Consegna gratuita per ordini da ${formatPrice(minimumOrderCents / 100)}.`;
    return "Consegna gratuita.";
  }
  if (zone.delivery_policy === "threshold") {
    const thresholdCents = freeMinimumCents ?? minimumOrderCents;
    if (thresholdCents === null) return "Soglia gratuita e costo di consegna da configurare.";
    const minimumDescription = minimumOrderCents !== null && minimumOrderCents > 0
      ? `Ordine minimo ${formatPrice(minimumOrderCents / 100)}; `
      : "";
    const paidDescription = feeCents === null
      ? `consegna a pagamento per ordini inferiori a ${formatPrice(thresholdCents / 100)}; costo da confermare con l'attività`
      : `consegna a pagamento: ${formatPrice(feeCents / 100)} per ordini inferiori a ${formatPrice(thresholdCents / 100)}`;
    return `${minimumDescription}${paidDescription}; gratuita da ${formatPrice(thresholdCents / 100)}.`;
  }
  if (zone.delivery_policy === "paid") {
    return feeCents === null
      ? "Consegna a pagamento, costo da confermare con l'attività."
      : `Consegna a pagamento: ${formatPrice(feeCents / 100)}.`;
  }
  return "Costo di consegna da confermare con l'attività.";
}

function getDeliveryQuote(zone, subtotalCents, freeThresholdSubtotalCents = subtotalCents) {
  if (!zone) {
    return {
      state: "unknown",
      costCents: null,
      minimumOrderCents: null,
      label: "Da stimare",
      note: "Seleziona il comune per conoscere costo e modalità di consegna.",
    };
  }

  const freeMinimumCents = optionalPriceInCents(zone.free_delivery_minimum);
  const configuredMinimumCents = optionalPriceInCents(zone.minimum_order_amount);
  const minimumOrderCents = configuredMinimumCents ?? (zone.delivery_policy === "threshold" ? freeMinimumCents : null);
  const configuredFeeCents = optionalPriceInCents(zone.delivery_fee);
  const minimumReached = minimumOrderCents === null || subtotalCents >= minimumOrderCents;
  if (!minimumReached) {
    const amountToMinimumCents = minimumOrderCents - subtotalCents;
    const freeThresholdNote = zone.delivery_policy === "threshold" && freeMinimumCents !== null
      ? ` La consegna è gratuita da ${formatPrice(freeMinimumCents / 100)}.`
      : "";
    return {
      state: "minimum",
      costCents: null,
      minimumOrderCents,
      minimumReached: false,
      label: zone.delivery_policy === "threshold" && freeMinimumCents !== null
        ? `Gratis da ${formatPrice(freeMinimumCents / 100)}`
        : "Minimo non raggiunto",
      note: `Ordine minimo ${formatPrice(minimumOrderCents / 100)}: aggiungi ${formatPrice(amountToMinimumCents / 100)} per inviare la richiesta.${freeThresholdNote}`,
    };
  }
  let costCents = null;
  let stateName = "unknown";
  let label = "Da confermare";
  let note = deliveryPolicyDescription(zone);

  if (zone.delivery_policy === "free") {
    costCents = 0;
    stateName = "free";
    label = "Gratuita";
  } else if (zone.delivery_policy === "threshold") {
    if (freeMinimumCents !== null && freeThresholdSubtotalCents >= freeMinimumCents) {
      costCents = 0;
      stateName = "free";
      label = "Gratuita";
      note = `Consegna gratuita: raggiunta la soglia di ${formatPrice(freeMinimumCents / 100)}.`;
    } else if (freeMinimumCents !== null) {
      costCents = configuredFeeCents;
      stateName = configuredFeeCents === null ? "unknown" : "paid";
      label = configuredFeeCents === null ? "A pagamento" : formatPrice(configuredFeeCents / 100);
      note = deliveryPolicyDescription(zone);
    } else {
      label = "Soglia da definire";
      note = "Soglia di consegna gratuita da configurare.";
    }
  } else if (zone.delivery_policy === "paid") {
    costCents = configuredFeeCents;
    stateName = "paid";
    label = configuredFeeCents === null ? "A pagamento" : formatPrice(configuredFeeCents / 100);
    note = configuredFeeCents === null
      ? "Consegna a pagamento; costo da confermare con l'attività."
      : `Consegna a pagamento: ${formatPrice(configuredFeeCents / 100)}.`;
  }

  return { state: stateName, costCents, minimumOrderCents, minimumReached: true, label, note };
}

function updateDeliveryEstimate() {
  renderCart();
}

function getDeliveryZones() {
  if (!Array.isArray(state.site.delivery_zones)) return [];
  return state.site.delivery_zones.filter((zone) =>
    zone && zone.id && Array.isArray(zone.locations),
  );
}

function deliveryZoneLabel(zone) {
  const match = String(zone.id || "").match(/^zona-(\d+)$/i);
  return match ? `Zona ${match[1]}` : String(zone.name || "Zona di consegna");
}

function renderDeliveryInfo() {
  const zones = getDeliveryZones();
  const colors = ["#c95e47", "#5e874b", "#4f7892"];
  state.selectedDeliveryZoneId = zones[0]?.id || null;
  const zone1 = zones.find((zone) => zone.id === "zona-01");
  const zone2 = zones.find((zone) => zone.id === "zona-02");
  const zone3 = zones.find((zone) => zone.id === "zona-03");
  if (elements.zone1DeliveryFaq) {
    elements.zone1DeliveryFaq.textContent = zone1 ? deliveryPolicyDescription(zone1) : "Condizioni da confermare.";
  }
  if (elements.zone2DeliveryFaq) {
    elements.zone2DeliveryFaq.textContent = zone2 ? deliveryPolicyDescription(zone2) : "Condizioni da confermare.";
  }
  if (elements.zone3DeliveryFaq) {
    elements.zone3DeliveryFaq.textContent = zone3 ? deliveryPolicyDescription(zone3) : "Condizioni da confermare.";
  }

  if (elements.deliveryZones) {
    elements.deliveryZones.innerHTML = zones.map((zone, index) => {
      const locations = zone.locations.map((location) => String(location.name || "").trim()).filter(Boolean);
      const details = String(zone.delivery_time || "").trim();
      const description = [locations.join(", "), details, deliveryPolicyDescription(zone)].filter(Boolean).join(". ");
      return `
        <article class="delivery-zone${index === 0 ? " delivery-zone--primary" : ""}">
          <span class="delivery-zone__label">ZONA ${String(index + 1).padStart(2, "0")}</span>
          <h3>${escapeHtml(zone.name || "Zona di consegna")}</h3>
          <p>${escapeHtml(description)}</p>
        </article>
      `;
    }).join("");
  }

  if (elements.deliveryDisclaimer) {
    elements.deliveryDisclaimer.textContent = state.site.delivery_note ||
      "Tempi indicativi, soggetti a disponibilità e indirizzo. La consegna viene concordata con l'attività.";
  }

  if (elements.deliveryNote) {
    elements.deliveryNote.textContent = state.site.delivery_note ||
      "Tempi indicativi, soggetti a disponibilità e indirizzo. La consegna viene concordata con l'attività.";
  }

  if (elements.deliveryDialogZones) {
    elements.deliveryDialogZones.innerHTML = zones.map((zone, index) => {
      const locations = zone.locations.map((location) => String(location.name || "").trim()).filter(Boolean);
      const locationText = locations.join(", ");
      return `
        <button
          class="delivery-dialog__zone${index === 0 ? " is-active" : ""}"
          type="button"
          data-delivery-zone="${escapeHtml(zone.id)}"
          style="--zone-color: ${colors[index % colors.length]}"
          aria-pressed="${index === 0}"
        >
          <strong>${escapeHtml(deliveryZoneLabel(zone))}</strong>
          <span>${escapeHtml(zone.delivery_time || "Spedizione standard, tempi variabili")}</span>
          <small>${escapeHtml(locationText)}</small>
          <small>${escapeHtml(deliveryPolicyDescription(zone))}</small>
        </button>
      `;
    }).join("");
  }
}

function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletPromise) return leafletPromise;

  leafletPromise = new Promise((resolve, reject) => {
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    stylesheet.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
    stylesheet.crossOrigin = "anonymous";
    const stylesheetLoaded = new Promise((load, fail) => {
      stylesheet.addEventListener("load", load, { once: true });
      stylesheet.addEventListener("error", fail, { once: true });
    });

    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
    script.crossOrigin = "anonymous";
    const scriptLoaded = new Promise((load, fail) => {
      script.addEventListener("load", load, { once: true });
      script.addEventListener("error", fail, { once: true });
    });

    Promise.all([stylesheetLoaded, scriptLoaded]).then(() => resolve(window.L), reject);
    document.head.append(stylesheet);
    document.head.append(script);
  });

  return leafletPromise;
}

function selectDeliveryZone(zoneId, fitMap = true) {
  const zone = getDeliveryZones().find((item) => item.id === zoneId);
  if (!zone) return;
  state.selectedDeliveryZoneId = zoneId;

  elements.deliveryDialogZones.querySelectorAll("[data-delivery-zone]").forEach((button) => {
    const isActive = button.dataset.deliveryZone === zoneId;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });

  state.deliveryMarkers.forEach((markers, markerZoneId) => {
    markers.forEach((marker) => {
      const isActive = markerZoneId === zoneId;
      marker.setStyle({ radius: isActive ? 9 : 7, weight: isActive ? 3 : 1.5, fillOpacity: isActive ? 0.95 : 0.7 });
    });
  });

  if (!fitMap || !state.deliveryMap) return;
  const locations = zone.locations.filter((location) =>
    Number.isFinite(Number(location.lat)) && Number.isFinite(Number(location.lon)),
  );
  if (locations.length === 1) {
    state.deliveryMap.setView([Number(locations[0].lat), Number(locations[0].lon)], 12);
  } else if (locations.length > 1) {
    const bounds = locations.map((location) => [Number(location.lat), Number(location.lon)]);
    state.deliveryMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
  }
}

async function initializeDeliveryMap() {
  if (state.deliveryMap) {
    window.requestAnimationFrame(() => state.deliveryMap.invalidateSize());
    return;
  }

  elements.deliveryMapStatus.textContent = "Caricamento mappa...";
  const zones = getDeliveryZones();
  const locations = zones.flatMap((zone) => zone.locations.filter((location) =>
    location.name && Number.isFinite(Number(location.lat)) && Number.isFinite(Number(location.lon)),
  ));
  if (!locations.length) {
    elements.deliveryMapStatus.textContent = "Le zone di consegna non sono disponibili.";
    return;
  }

  try {
    await loadLeaflet();
  } catch {
    const message = document.createElement("p");
    message.textContent = "La mappa interattiva non è raggiungibile.";
    const link = document.createElement("a");
    link.href = "https://www.openstreetmap.org/#map=10/40.8329/14.7918";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Apri la zona su OpenStreetMap";
    elements.deliveryMap.replaceChildren(message, link);
    elements.deliveryMapStatus.textContent = "";
    return;
  }

  const mapLibrary = window.L;
  elements.deliveryMap.replaceChildren();
  state.deliveryMap = mapLibrary.map(elements.deliveryMap, { scrollWheelZoom: false });
  mapLibrary.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(state.deliveryMap);

  const colors = ["#c95e47", "#5e874b", "#4f7892"];
  const allCoordinates = [];
  zones.forEach((zone, index) => {
    const color = colors[index % colors.length];
    const markers = zone.locations
      .filter((location) => location.name && Number.isFinite(Number(location.lat)) && Number.isFinite(Number(location.lon)))
      .map((location) => {
        const coordinates = [Number(location.lat), Number(location.lon)];
        allCoordinates.push(coordinates);
        const marker = mapLibrary.circleMarker(coordinates, {
          radius: 7,
          color,
          fillColor: color,
          fillOpacity: 0.7,
          weight: 1.5,
        }).addTo(state.deliveryMap);
        marker.bindTooltip(escapeHtml(location.name));
        marker.bindPopup(`<strong>${escapeHtml(location.name)}</strong><br>${escapeHtml(zone.delivery_time || "Spedizione standard, tempi variabili")}<br>${escapeHtml(deliveryPolicyDescription(zone))}`);
        marker.on("click", () => selectDeliveryZone(zone.id, false));
        return marker;
      });
    state.deliveryMarkers.set(zone.id, markers);
  });

  if (allCoordinates.length) {
    state.deliveryMap.fitBounds(allCoordinates, { padding: [30, 30], maxZoom: 10 });
  }
  if (state.selectedDeliveryZoneId) selectDeliveryZone(state.selectedDeliveryZoneId, false);
  elements.deliveryMapStatus.textContent = "";
  window.requestAnimationFrame(() => state.deliveryMap.invalidateSize());
}

function setupHeroCarousel() {
  if (!elements.hero || !elements.heroImage || !elements.heroToggle) return;

  const slides = [
    {
      image: "https://images.unsplash.com/photo-1608494133726-bb93324274c8?auto=format&fit=crop&w=2000&q=88",
      imageAlt: "Prodotti in carta per la casa",
      eyebrow: "LA CARTA, VICINO A TE",
      title: "La casa, il lavoro e l'ufficio, mai senza.",
      intro: "Carta igienica, rotoli cucina e tutto l'essenziale. Ordini in pochi passaggi, noi te li portiamo.",
      action: "Scegli i prodotti",
      actionHref: "/",
      openPromo: false,
      deliveryHighlight: "Montoro: circa 2 ore",
      deliverySecondary: "Comuni vicini: in giornata",
      caption: "UNA SCORTA IN MENO A CUI PENSARE",
    },
    {
      image: "https://images.unsplash.com/photo-1562240020-ce31ccb0fa7d?auto=format&fit=crop&w=2000&q=88",
      imageAlt: "Carta per stampante A4",
      eyebrow: "PROMO CASHBACK CARTAWAY",
      title: "Un Buono Tech per il tuo mese.",
      action: "Scopri la promo",
      actionHref: "#promo-dialog",
      openPromo: true,
      voucher: true,
      deliveryHighlight: "Un buono per cliente al mese",
      deliverySecondary: "60 giorni · 90 con ordine ricorrente · massimo 25 €",
      caption: "BUONO TECH · ORDINI SINGOLI E RICORRENTI",
    },
    {
      image: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=2000&q=88",
      imageAlt: "Scatole in magazzino, pronte per la consegna",
      eyebrow: "CONSEGNA LOCALE · ORDINI RICORRENTI",
      title: "La tua scorta, al ritmo giusto.",
      intro: "Scegli una consegna {frequency_days}: hai il 5% di sconto, prezzi bloccati per 12 mesi e puoi indicare un giorno fisso.",
      recurringVoucher: true,
      action: "Scopri le zone",
      actionHref: "#consegna",
      openPromo: false,
      deliveryHighlight: "Zona 01: gratuita, senza minimo",
      deliverySecondary: "Zona 02: 5 € sotto 30 €, gratuita da 30 € · Zona 03: spedizione a pagamento, 5 €",
      caption: "CONSEGNE PER ZONA · ORDINI RICORRENTI",
    },
    {
      image: "https://images.unsplash.com/photo-1608494133726-bb93324274c8?auto=format&fit=crop&w=2000&q=88",
      imageAlt: "Prodotti in carta per la casa",
      eyebrow: "SPEDIZIONI LOCALI · TRE ZONE",
      title: "La consegna giusta, nella tua zona.",
      intro: "Montoro: gratuita senza minimo, entro circa 2 ore. Nei comuni vicini è gratuita da 30 €; le località più lontane rientrano nella Zona 03, con spedizione a pagamento.",
      action: "Scopri le zone",
      actionHref: "#consegna",
      openPromo: false,
      deliveryHighlight: "Zona 01 · gratuita, senza minimo",
      deliverySecondary: "Zona 02 · 5 € sotto 30 €, gratuita da 30 € · Zona 03 · spedizione a pagamento: 5 €",
      caption: "TEMPI E COSTI CHIARI PER OGNI ZONA",
    },
  ];
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let currentSlide = 0;
  let rotationTimer = null;
  let isPaused = prefersReducedMotion.matches;
  let isPointerInside = false;
  let hasFocus = false;

  const renderSlide = (index) => {
    currentSlide = (index + slides.length) % slides.length;
    const slide = slides[currentSlide];
    const standardVoucherPercent = formatPercentage(techVoucherPercent(false));
    const recurringVoucherPercent = formatPercentage(techVoucherPercent(true));
    elements.heroImage.src = slide.image;
    elements.heroImage.alt = slide.imageAlt;
    elements.heroEyebrow.textContent = slide.eyebrow;
    elements.heroTitle.textContent = slide.title;
    elements.heroIntro.textContent = slide.voucher
      ? `Sul primo ordine del mese: ${standardVoucherPercent}% con un ordine singolo e ${recurringVoucherPercent}% con un ordine ricorrente, fino a ${formatPrice(techVoucherMaximumCents() / 100)}. L'attivazione è verificata dall'attività.`
      : slide.recurringVoucher
      ? `${slide.intro.replace("{frequency_days}", formatRecurringFrequencyList())} Con l'ordine ricorrente, la validità del Buono Tech si estende a ${techVoucherValidityText(true)} dalla consegna.`
        : slide.intro;
    elements.heroActionLabel.textContent = slide.action;
    elements.heroAction.href = slide.actionHref;
    elements.heroAction.dataset.openPromo = String(slide.openPromo);
    elements.heroDeliveryHighlight.textContent = slide.voucher
      ? `${standardVoucherPercent}% singolo · ${recurringVoucherPercent}% ricorrente · massimo ${formatPrice(techVoucherMaximumCents() / 100)}`
      : slide.deliveryHighlight;
    elements.heroDeliverySecondary.textContent = slide.voucher
      ? `${techVoucherValidityText()} dalla consegna · ${techVoucherValidityText(true)} con ordine ricorrente`
      : slide.deliverySecondary;
    elements.heroCaption.textContent = slide.voucher
      ? `BUONO TECH · ${standardVoucherPercent}% SINGOLO · ${recurringVoucherPercent}% RICORRENTE`
      : slide.caption;
    elements.heroSlideCount.textContent = `${String(currentSlide + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}`;
  };

  const updateRotation = () => {
    window.clearInterval(rotationTimer);
    rotationTimer = null;
    if (!isPaused && !isPointerInside && !hasFocus && !document.hidden) {
      rotationTimer = window.setInterval(() => renderSlide(currentSlide + 1), 7000);
    }
    const label = isPaused ? "Avvia lo scorrimento automatico" : "Metti in pausa lo scorrimento automatico";
    elements.heroToggle.textContent = isPaused ? "▶" : "⏸";
    elements.heroToggle.setAttribute("aria-label", label);
    elements.heroToggle.title = label;
  };

  slides.slice(1).forEach((slide) => {
    const image = new Image();
    image.src = slide.image;
  });
  renderSlide(0);

  elements.heroPrevious.addEventListener("click", () => {
    renderSlide(currentSlide - 1);
    updateRotation();
  });
  elements.heroNext.addEventListener("click", () => {
    renderSlide(currentSlide + 1);
    updateRotation();
  });
  elements.heroToggle.addEventListener("click", () => {
    isPaused = !isPaused;
    hasFocus = false;
    updateRotation();
  });
  elements.heroAction.addEventListener("click", (event) => {
    if (elements.heroAction.dataset.openPromo !== "true") return;
    event.preventDefault();
    elements.promoDialog.showModal();
  });
  elements.hero.addEventListener("mouseenter", () => {
    isPointerInside = true;
    updateRotation();
  });
  elements.hero.addEventListener("mouseleave", () => {
    isPointerInside = false;
    updateRotation();
  });
  elements.hero.addEventListener("focusin", () => {
    hasFocus = true;
    updateRotation();
  });
  elements.hero.addEventListener("focusout", (event) => {
    if (elements.hero.contains(event.relatedTarget)) return;
    hasFocus = false;
    updateRotation();
  });
  document.addEventListener("visibilitychange", updateRotation);
  prefersReducedMotion.addEventListener("change", (event) => {
    if (event.matches) isPaused = true;
    updateRotation();
  });
  updateRotation();
}

function setupEvents() {
  setupHeroCarousel();

  if (elements.categorySelect) {
    elements.categorySelect.addEventListener("change", (event) => {
      state.category = event.currentTarget.value;
      state.categorySubcategoriesExpanded = false;
      renderCategoryFilters();
      syncCatalogUrl();
      renderProducts();
    });
  }

  if (elements.productProfile) {
    elements.productProfile.addEventListener("change", (event) => {
      state.profile = event.currentTarget.value;
      state.category = "tutte";
      state.categorySubcategoriesExpanded = false;
      renderCategoryFilters();
      syncCatalogUrl();
      renderProducts();
    });
  }

  if (elements.categorySidebarToggle) {
    elements.categorySidebarToggle.addEventListener("click", () => {
      state.categorySubcategoriesExpanded = !state.categorySubcategoriesExpanded;
      renderCategoryFilters();
    });
  }

  window.matchMedia("(max-width: 1160px)").addEventListener("change", renderCategoryFilters);

  renderCategoryFilters();

  if (elements.productSearch) {
    elements.productSearch.addEventListener("input", (event) => {
      state.search = event.currentTarget.value;
      syncCatalogUrl();
      renderProducts();
    });
  }

  if (elements.productSort) {
    elements.productSort.addEventListener("change", (event) => {
      state.sort = event.currentTarget.value;
      syncCatalogUrl();
      renderProducts();
    });
  }

  elements.productViewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.productView;
      state.view = view === "list" || view === "excel" ? view : "grid";
      syncCatalogUrl();
      renderProducts();
    });
  });

  if (elements.catalogShare) {
    elements.catalogShare.addEventListener("click", async () => {
      syncCatalogUrl();
      const shareUrl = new URL(window.location.href);
      shareUrl.searchParams.delete("order");
      shareUrl.searchParams.delete("openCart");
      shareUrl.searchParams.delete("sheet");
      const sheetEntries = Object.entries(state.sheetQuantities)
        .map(([productId, quantity]) => [productId, normalizeSheetQuantity(quantity)])
        .filter(([, quantity]) => quantity > 0);
      if (sheetEntries.length > 0) {
        shareUrl.searchParams.set("sheet", JSON.stringify(sheetEntries));
        shareUrl.searchParams.set("view", "excel");
      }
      try {
        await navigator.clipboard.writeText(shareUrl.href);
        if (elements.catalogShareStatus) {
          elements.catalogShareStatus.textContent = sheetEntries.length > 0
            ? "Link Excel copiato. Verranno ripristinati filtri e quantità selezionate; il carrello resta separato."
            : "Link catalogo copiato. Verranno ripristinati filtri e vista, senza importare il carrello.";
        }
      } catch {
        if (elements.catalogShareStatus) elements.catalogShareStatus.textContent = "Copia del link non disponibile in questo browser.";
      }
    });
  }

  if (elements.productSheetAddAll) {
    elements.productSheetAddAll.addEventListener("click", addSelectedProductsToCart);
  }

  [elements.promoOpen, elements.promoOpenTop].forEach((button) => {
    button?.addEventListener("click", () => {
      openQuickMessage(button.dataset.activeQuickMessage || "tech");
    });
  });
  if (elements.promoDialog) {
    elements.promoDialog.addEventListener("click", (event) => {
      if (event.target === elements.promoDialog) elements.promoDialog.close();
    });
    elements.promoDialog.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      elements.promoDialog.close();
    });
  }

  if (elements.deliveryOpen && elements.deliveryDialog) {
    elements.deliveryOpen.addEventListener("click", () => {
      elements.deliveryDialog.showModal();
      void initializeDeliveryMap();
    });
    elements.deliveryDialog.addEventListener("click", (event) => {
      if (event.target === elements.deliveryDialog) elements.deliveryDialog.close();
    });
  }
  if (elements.deliveryDialogZones) {
    elements.deliveryDialogZones.addEventListener("click", (event) => {
      const button = event.target.closest("[data-delivery-zone]");
      if (button) selectDeliveryZone(button.dataset.deliveryZone);
    });
  }

  if (elements.productGrid) {
    elements.productGrid.addEventListener("click", (event) => {
      const productLink = event.target.closest("[data-open-product]");
      if (productLink) {
        event.preventDefault();
        openProductDialog(productLink.dataset.openProduct);
        return;
      }
      const button = event.target.closest("[data-add-to-cart]");
      if (button) addToCart(button.dataset.addToCart);
    });
  }

  if (elements.productSheetBody) {
    elements.productSheetBody.addEventListener("input", (event) => {
      const input = event.target.closest("[data-sheet-quantity]");
      const productId = input?.closest("tr")?.dataset.sheetProductId;
      if (!input || !productId) return;
      state.sheetQuantities[productId] = normalizeSheetQuantity(input.value);
      refreshProductSheetOrderBar();
    });
    elements.productSheetBody.addEventListener("change", (event) => {
      const input = event.target.closest("[data-sheet-quantity]");
      const productId = input?.closest("tr")?.dataset.sheetProductId;
      if (!input || !productId) return;
      const quantity = normalizeSheetQuantity(input.value);
      input.value = String(quantity);
      state.sheetQuantities[productId] = quantity;
      refreshProductSheetOrderBar();
    });
    elements.productSheetBody.addEventListener("click", (event) => {
      const stepButton = event.target.closest("[data-sheet-step]");
      if (stepButton) {
        const row = stepButton.closest("tr");
        const input = row?.querySelector("[data-sheet-quantity]");
        const productId = row?.dataset.sheetProductId;
        if (!input || !productId) return;
        const quantity = Math.min(999, Math.max(0, normalizeSheetQuantity(input.value) + Number(stepButton.dataset.sheetStep)));
        input.value = String(quantity);
        state.sheetQuantities[productId] = quantity;
        refreshProductSheetOrderBar();
        return;
      }

      const productLink = event.target.closest("[data-open-product]");
      if (!productLink) return;
      event.preventDefault();
      openProductDialog(productLink.dataset.openProduct);
    });
  }

  if (elements.productSheet) {
    elements.productSheet.addEventListener("click", (event) => {
      const sortableHeader = event.target.closest("th[data-sheet-sort-header]");
      if (sortableHeader) sortSheetColumn(sortableHeader.dataset.sheetSortHeader);
    });
  }

  if (elements.productDialog) {
    elements.productDialogPrevious.addEventListener("click", () => {
      renderProductDialogImage(state.dialogImageIndex - 1);
    });
    elements.productDialogNext.addEventListener("click", () => {
      renderProductDialogImage(state.dialogImageIndex + 1);
    });
    elements.productDialogThumbnails.addEventListener("click", (event) => {
      const thumbnail = event.target.closest("[data-gallery-index]");
      if (thumbnail) renderProductDialogImage(Number(thumbnail.dataset.galleryIndex));
    });
    elements.productDialog.addEventListener("click", (event) => {
      if (event.target === elements.productDialog) elements.productDialog.close();
    });
    elements.productDialogAdd.addEventListener("click", () => {
      if (!state.dialogProduct) return;
      addToCart(state.dialogProduct.id);
      elements.productDialog.close();
    });
  }

  if (elements.detailImagePrevious) {
    elements.detailImagePrevious.addEventListener("click", () => {
      renderDetailImage(state.detailImageIndex - 1);
    });
    elements.detailImageNext.addEventListener("click", () => {
      renderDetailImage(state.detailImageIndex + 1);
    });
    elements.detailThumbnails.addEventListener("click", (event) => {
      const thumbnail = event.target.closest("[data-detail-image-index]");
      if (thumbnail) renderDetailImage(Number(thumbnail.dataset.detailImageIndex));
    });
    elements.detailAdd.addEventListener("click", () => {
      if (state.detailProduct) addToCart(state.detailProduct.id);
    });
  }

  elements.cartOpen.addEventListener("click", () => {
    elements.cartDialog.showModal();
    document.documentElement.classList.add("cart-is-open");
  });

  if (elements.cartClear) {
    elements.cartClear.addEventListener("click", () => {
      if (elements.cartClear.disabled) return;
      state.cart = {};
      saveCart();
      clearCheckoutFeedback();
      renderCart();
      showMessage("Carrello svuotato.");
    });
  }

  if (elements.cartShare) {
    elements.cartShare.addEventListener("click", async () => {
      const items = cartEntries();
      if (!items.length) return;

      const shareUrl = buildCartShareUrl(items);
      try {
        await navigator.clipboard.writeText(shareUrl.href);
        showMessage("Link del carrello copiato. Aprendolo, il carrello verrà ricreato e aperto.");
      } catch {
        showMessage("Copia del link non disponibile in questo browser.");
      }
    });
  }

  elements.cartItems.addEventListener("click", (event) => {
    const button = event.target.closest("[data-cart-change]");
    if (!button) return;
    changeQuantity(button.dataset.productId, Number(button.dataset.cartChange));
  });

  elements.cartItems.addEventListener("change", (event) => {
    const input = event.target.closest("[data-cart-quantity]");
    if (!input) return;
    const quantity = Number(input.value);
    if (!Number.isSafeInteger(quantity) || quantity < 1) {
      input.value = String(state.cart[input.dataset.productId] || 1);
      return;
    }
    setQuantity(input.dataset.productId, quantity);
  });

  elements.cartDialog.addEventListener("click", (event) => {
    if (event.target === elements.cartDialog) elements.cartDialog.close();
  });
  elements.cartDialog.addEventListener("close", () => {
    document.documentElement.classList.remove("cart-is-open");
  });

  document.querySelector("#continue-shopping").addEventListener("click", () => {
    elements.cartDialog.close();
    document.documentElement.classList.remove("cart-is-open");
    const productsSection = document.querySelector("#prodotti");
    if (productsSection) {
      productsSection.scrollIntoView({ behavior: "smooth" });
    } else {
      window.location.assign("/");
    }
  });

  elements.deliveryTown.addEventListener("change", () => {
    const isOther = elements.deliveryTown.value === "altro";
    elements.otherTownField.hidden = !isOther;
    elements.otherTown.required = isOther;
    if (!isOther) elements.otherTown.value = "";
    updateDeliveryEstimate();
  });

  elements.otherTown.addEventListener("input", updateDeliveryEstimate);

  elements.recurringOrder.addEventListener("change", updateRecurringControls);

  if (elements.preferredDate) {
    const today = new Date();
    elements.preferredDate.min = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, "0"),
      String(today.getDate()).padStart(2, "0"),
    ].join("-");
  }

  if (elements.preferredTimeStart && elements.preferredTimeEnd) {
    let autoFilledTimeField = null;
    const fillEmptyTimeField = (source, target) => {
      const targetWasAutoFilled = autoFilledTimeField === target;
      if (source.value && (!target.value || targetWasAutoFilled)) {
        target.value = source.value;
        autoFilledTimeField = target;
      } else if (!source.value && targetWasAutoFilled) {
        target.value = "";
        autoFilledTimeField = null;
      } else if (autoFilledTimeField === source) {
        autoFilledTimeField = null;
      }
    };
    elements.preferredTimeStart.addEventListener("change", () => {
      fillEmptyTimeField(elements.preferredTimeStart, elements.preferredTimeEnd);
    });
    elements.preferredTimeEnd.addEventListener("change", () => {
      fillEmptyTimeField(elements.preferredTimeEnd, elements.preferredTimeStart);
    });
  }

  elements.menuToggle.addEventListener("click", () => {
    const expanded = elements.menuToggle.getAttribute("aria-expanded") === "true";
    elements.menuToggle.setAttribute("aria-expanded", String(!expanded));
    elements.menuToggle.setAttribute("aria-label", expanded ? "Apri il menu" : "Chiudi il menu");
    elements.navigation.classList.toggle("is-open", !expanded);
  });

  elements.navigation.addEventListener("click", (event) => {
    if (!event.target.closest("a")) return;
    elements.menuToggle.setAttribute("aria-expanded", "false");
    elements.menuToggle.setAttribute("aria-label", "Apri il menu");
    elements.navigation.classList.remove("is-open");
  });

  elements.checkoutForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.orderSubmitting) return;
    clearCheckoutFeedback();
    const items = cartEntries();
    if (!items.length) return;
    if (items.some(({ product }) => productPriceInCents(product) === null)) {
      showCheckoutFeedback("Configura le aliquote IVA delle categorie prima di inviare la richiesta.", "error");
      return;
    }

    const emailSettings = state.site.emailjs || {};
    const publicKey = String(emailSettings.public_key || "").trim();
    const serviceId = String(emailSettings.service_id || "").trim();
    const templateId = String(emailSettings.template_id || "").trim();
    if (!publicKey || !serviceId || !templateId) {
      showCheckoutFeedback("Invio email non configurato. Contatta l'attività per completare la richiesta.", "error");
      return;
    }
    if (!window.emailjs) {
      showCheckoutFeedback("Il servizio email non è disponibile. Riprova tra poco.", "error");
      return;
    }

    const formData = new FormData(elements.checkoutForm);
    const name = String(formData.get("name") || "").trim();
    const customerEmail = String(formData.get("email") || "").trim();
    const phone = String(formData.get("phone") || "").trim();
    const address = String(formData.get("address") || "").trim();
    const selectedTown = String(formData.get("city") || "");
    const town = selectedTown === "altro" ? String(formData.get("other-town") || "").trim() : selectedTown;
    const preferredDate = String(formData.get("preferred-date") || "").trim();
    const preferredTimeStart = String(formData.get("preferred-time-start") || "").trim();
    const preferredTimeEnd = String(formData.get("preferred-time-end") || "").trim();
    const preferredTimeSlot = preferredTimeStart && preferredTimeEnd
      ? `${preferredTimeStart} - ${preferredTimeEnd}`
      : preferredTimeStart
        ? `dalle ${preferredTimeStart}`
        : preferredTimeEnd
          ? `entro le ${preferredTimeEnd}`
          : "";
    const recurringOrder = formData.get("recurring-order") === "yes";
    const recurringFrequency = String(formData.get("recurring-frequency") || "").trim();
    const recurringDay = String(formData.get("recurring-day") || "").trim();
    const notes = String(formData.get("notes") || "").trim();
    const discountPercent = getRecurringDiscountPercent();
    const recurringConfig = state.site.recurring_order || {};
    const configuredMonths = Number(recurringConfig.price_lock_months);
    const priceLockMonths = Number.isInteger(configuredMonths) && configuredMonths > 0 ? configuredMonths : 12;
    const fullSubtotalCents = items.reduce(
      (total, item) => total + productPriceInCents(item.product) * item.quantity,
      0,
    );
    const subtotalCents = items.reduce(
      (total, item) => total + (recurringOrder ? productRecurringPriceInCents(item.product) : productPriceInCents(item.product)) * item.quantity,
      0,
    );
    const deliveryZone = findDeliveryZoneForTown(town);
    const deliveryQuote = getDeliveryQuote(deliveryZone, subtotalCents, fullSubtotalCents);
    if (deliveryQuote.minimumReached === false) {
      showCheckoutFeedback(`Ordine minimo ${formatPrice(deliveryQuote.minimumOrderCents / 100)}: aggiungi altri prodotti per continuare.`, "error");
      return;
    }
    const voucherId = window.crypto?.randomUUID
      ? `BT-${window.crypto.randomUUID().toUpperCase()}`
      : `BT-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 10).toUpperCase()}`;
    const voucherValueCents = techVoucherAmountCents(subtotalCents, recurringOrder);
    const orderId = window.crypto?.randomUUID
      ? window.crypto.randomUUID().slice(0, 8).toUpperCase()
      : `CW-${Date.now()}`;
    const emailOrders = items.map(({ product, quantity }) => {
      const unitPriceCents = recurringOrder ? productRecurringPriceInCents(product) : productPriceInCents(product);
      return {
        name: productNameWithFormat(product),
        units: quantity,
        price: formatPrice(unitPriceCents / 100),
        line_total: formatPrice((unitPriceCents * quantity) / 100),
        image_url: safeImageUrl(product.image || fallbackImage),
      };
    });
    const vatAmountCents = orderVatAmountCents(items, recurringOrder);
    const vatSummary = vatAmountCents === null
      ? pricesIncludeVat()
        ? "Inclusa nei prezzi; aliquote per categoria da configurare"
        : "Aliquote IVA per categoria da configurare"
      : `${pricesIncludeVat() ? "Inclusa nei prezzi: " : ""}${formatPrice(vatAmountCents / 100)}`;
    const shippingCost = deliveryQuote.costCents === null
      ? "Da confermare"
      : deliveryQuote.costCents === 0
        ? "Gratuita"
        : formatPrice(deliveryQuote.costCents / 100);
    const totalCost = deliveryQuote.costCents === null
      ? `${formatPrice(subtotalCents / 100)} + consegna da confermare`
      : formatPrice((subtotalCents + deliveryQuote.costCents) / 100);
    const preferredDeliveryDate = preferredDate
      ? new Date(`${preferredDate}T00:00:00`).toLocaleDateString("it-IT")
      : "Non indicata";
    const deliveryZoneName = deliveryZone
      ? `${deliveryZoneLabel(deliveryZone)} - ${String(deliveryZone.name || "").trim()}`
      : "Da verificare";
    const estimatedDeliveryTime = String(deliveryZone?.delivery_time || "").trim() || "Da confermare";
    const templateParams = {
      brand: String(state.site.brand || "Cartaway"),
      website_url: window.location.origin,
      cart_url: buildCartShareUrl(items).href,
      order_id: orderId,
      orders: emailOrders,
      cost: { shipping: shippingCost, tax: vatSummary, total: totalCost },
      tech_voucher_id: voucherId,
      tech_voucher_value: formatPrice(voucherValueCents / 100),
      tech_voucher_percent: `${formatPercentage(techVoucherPercent(recurringOrder))}%`,
      tech_voucher_standard_percent: `${formatPercentage(techVoucherPercent(false))}%`,
      tech_voucher_recurring_percent: `${formatPercentage(techVoucherPercent(true))}%`,
      tech_voucher_maximum: formatPrice(techVoucherMaximumCents() / 100),
      tech_voucher_validity: techVoucherValidityText(recurringOrder),
      customer_name: name || "Cliente",
      customer_email: customerEmail,
      customer_phone: phone,
      delivery_city: town || "Da specificare",
      delivery_address: address || "Da specificare",
      delivery_zone: deliveryZoneName,
      estimated_delivery_time: estimatedDeliveryTime,
      preferred_delivery_date: preferredDeliveryDate,
      preferred_delivery_time: preferredTimeSlot || "Non indicata",
      recurring_order: recurringOrder ? "Sì" : "No",
      recurring_frequency: recurringOrder ? formatRecurringFrequency(Number(recurringFrequency)) : "Non applicabile",
      recurring_day: recurringOrder && recurringDay ? recurringDay : "Non indicato",
      recurring_discount: recurringOrder ? `${formatPercentage(discountPercent)}%` : "Nessuno",
      price_lock_months: recurringOrder ? `${priceLockMonths} mesi` : "Non applicabile",
      delivery_notes: notes || "Nessuna",
    };

    state.orderSubmitting = true;
    elements.orderSubmitLabel.textContent = "Invio in corso...";
    renderCart();
    try {
      window.emailjs.init({ publicKey });
      await window.emailjs.send(serviceId, templateId, {
        ...templateParams,
        email: customerEmail,
        reply_to: String(state.site.email || "").trim(),
      });
      state.cart = {};
      saveCart();
      elements.checkoutForm.reset();
      elements.otherTownField.hidden = true;
      elements.otherTown.required = false;
      updateRecurringControls();
      showCheckoutFeedback(`Riepilogo inviato a ${customerEmail} e all'attività. Il carrello è stato svuotato. Verificheremo la disponibilità; se un prodotto non è disponibile, ti contatteremo noi.`, "success");
    } catch {
      showCheckoutFeedback("Invio email non riuscito. Il carrello è stato conservato; riprova tra poco.", "error");
    } finally {
      state.orderSubmitting = false;
      elements.orderSubmitLabel.textContent = "Ricevi riepilogo via email";
      renderCart();
    }
  });
}

async function initializeShop() {
  setupEvents();
  const promoFaq = document.querySelector("#buono-tech-faq");
  if (window.location.hash === "#buono-tech-faq" && promoFaq instanceof HTMLDetailsElement) {
    promoFaq.open = true;
  }
  setupQuickMessageRotation();
  renderCart();

  try {
    const [siteResponse, productsResponse] = await Promise.all([
      fetch("data/site.json", { cache: "no-store" }),
      fetch("data/products.json", { cache: "no-store" }),
    ]);
    if (!siteResponse.ok || !productsResponse.ok) throw new Error("Impossibile caricare i dati del negozio.");

    const [site, catalog] = await Promise.all([siteResponse.json(), productsResponse.json()]);
    state.site = site;
    renderProfileFilter();
    configureTechVoucher();
    configureRecurringOrder();
    configureQuickMessages();
    updateRecurringControls();
    state.products = Array.isArray(catalog.products) ? catalog.products : [];
    restoreCatalogStateFromUrl();
    state.sheetQuantities = parseSharedSheet(state.sharedSheet);
    const sharedCart = parseSharedOrder(state.sharedOrder);
    if (sharedCart !== null) {
      state.cart = sharedCart;
      state.openSharedCart = state.openSharedCart && Object.keys(sharedCart).length > 0;
      if (elements.catalogShareStatus) {
        elements.catalogShareStatus.textContent = Object.keys(sharedCart).length > 0
          ? "Ordine condiviso caricato nel carrello."
          : "Gli articoli dell'ordine condiviso non sono più disponibili.";
      }
    } else if (state.sharedOrder !== null) {
      state.openSharedCart = false;
    }
    state.cart = Object.fromEntries(
      Object.entries(state.cart).filter(([id]) =>
        state.products.some((product) => product.id === id && product.available !== false),
      ),
    );
    saveCart();
    renderSiteDetails();
    if (elements.deliveryDialog?.open) void initializeDeliveryMap();
    renderProducts();
    renderProductDetail();
    renderCart();
    if (state.openSharedCart && !elements.cartDialog.open) {
      elements.cartDialog.showModal();
      document.documentElement.classList.add("cart-is-open");
    }
  } catch (error) {
    console.error(error);
    if (elements.productCount) elements.productCount.textContent = "Catalogo non disponibile. Riprova tra poco.";
    if (elements.productGrid) elements.productGrid.replaceChildren();
    if (elements.emptyState) elements.emptyState.hidden = true;
    if (elements.productDetail) elements.productDetail.hidden = true;
    if (elements.productNotFound) {
      const heading = elements.productNotFound.querySelector("h1");
      if (heading) heading.textContent = "Prodotto non disponibile";
      elements.productNotFound.hidden = false;
    }
  }
}

initializeShop();
