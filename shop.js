const cartStorageKey = "cartaway-cart-v1";
const fallbackImage =
  "https://images.unsplash.com/photo-1608494133726-bb93324274c8?auto=format&fit=crop&w=900&q=82";
const euro = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
});

const state = {
  page: document.body.dataset.page || "home",
  products: [],
  site: {},
  cart: readCart(),
  category: "tutte",
  search: "",
  sort: "featured",
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
  cartCount: document.querySelector("#cart-count"),
  cartDialog: document.querySelector("#cart-dialog"),
  cartEmpty: document.querySelector("#cart-empty"),
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
  cartCashbackNote: document.querySelector("#cart-cashback-note"),
  categoryButtons: [...document.querySelectorAll("[data-category]")],
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
  otherTown: document.querySelector("#other-town"),
  otherTownField: document.querySelector("#other-town-field"),
  productCount: document.querySelector("#product-count"),
  productGrid: document.querySelector("#product-grid"),
  productSearch: document.querySelector("#product-search"),
  productSort: document.querySelector("#product-sort"),
  preferredTimeStart: document.querySelector("#preferred-time-start"),
  preferredTimeEnd: document.querySelector("#preferred-time-end"),
  promoDialog: document.querySelector("#promo-dialog"),
  promoOpen: document.querySelector("#promo-open"),
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

function recurringPriceInCents(price) {
  return Math.round(priceInCents(price) * (100 - getRecurringDiscountPercent()) / 100);
}

function recurringFrequencyDays() {
  const configuredDays = state.site.recurring_order?.frequency_days;
  const days = Array.isArray(configuredDays)
    ? [...new Set(configuredDays.map(Number).filter((value) => Number.isInteger(value) && value > 0))]
    : [];
  return days.length ? days : [30, 60];
}

function techVoucherPercent() {
  const value = Number(state.site.tech_voucher?.percent);
  return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 50;
}

function techVoucherMaximumCents() {
  return optionalPriceInCents(state.site.tech_voucher?.maximum_amount) ?? 2500;
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

function techVoucherAmountCents(subtotalCents) {
  return Math.min(Math.round(subtotalCents * techVoucherPercent() / 100), techVoucherMaximumCents());
}

function configureTechVoucher() {
  document.querySelectorAll("[data-tech-voucher-percent]").forEach((element) => {
    element.textContent = `${formatPercentage(techVoucherPercent())}%`;
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
    option.textContent = `Ogni ${days} giorni`;
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
  if (elements.recurringFrequencyFaq) {
    elements.recurringFrequencyFaq.textContent = `${frequencies.join(" o ")} giorni`;
  }
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

function productCard(product) {
  const id = escapeHtml(product.id);
  const name = String(product.name || "Prodotto");
  const productUrl = `prodotto.html?id=${encodeURIComponent(String(product.id || ""))}`;
  const images = productImages(product);
  const imageCount = images.length;
  return `
    <article class="product-card">
      <div class="product-card__visual">
        <a class="product-card__image-button" href="${escapeHtml(productUrl)}" data-open-product="${id}" aria-label="Apri anteprima di ${escapeHtml(name)}">
          <img src="${escapeHtml(safeImageUrl(images[0] || fallbackImage))}" alt="" loading="lazy" decoding="async" />
        </a>
        <span class="product-card__category">${escapeHtml(product.category || "Carta")}</span>
        ${state.page === "home" && product.featured === true ? `<span class="product-card__featured">In evidenza</span>` : ""}
        ${imageCount > 1 ? `<span class="product-card__image-count">${imageCount} foto</span>` : ""}
      </div>
      <div class="product-card__content">
        <h3><a class="product-card__title" href="${escapeHtml(productUrl)}" data-open-product="${id}">${escapeHtml(name)}</a></h3>
        <p class="product-card__unit">${escapeHtml(product.unit || "")}</p>
        <p class="product-card__description">${escapeHtml(product.description || "")}</p>
        <div class="product-card__purchase">
          <strong class="product-card__price">${escapeHtml(formatPrice(product.price))}</strong>
          <button class="add-button" type="button" data-add-to-cart="${id}" aria-label="Aggiungi ${escapeHtml(name)} al carrello">
            <span class="add-button__plus" aria-hidden="true">+</span><span>Aggiungi</span>
          </button>
        </div>
      </div>
    </article>
  `;
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
  elements.productDialogCategory.textContent = product.category || "Carta";
  elements.productDialogUnit.textContent = product.unit || "";
  elements.productDialogPrice.textContent = formatPrice(product.price);
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
    document.title = "Prodotto non trovato — Cartaway";
    return;
  }

  state.detailProduct = product;
  state.detailImages = productImages(product);
  if (state.detailImages.length === 0) state.detailImages = [fallbackImage];
  elements.productDetail.hidden = false;
  elements.productNotFound.hidden = true;
  elements.detailTitle.textContent = product.name || "Prodotto";
  elements.detailCategory.textContent = product.category || "Carta";
  elements.detailUnit.textContent = product.unit || "";
  elements.detailPrice.textContent = formatPrice(product.price);
  elements.detailDescription.textContent = product.description || "";
  elements.detailBreadcrumbTitle.textContent = product.name || "Prodotto";
  document.title = `${product.name || "Prodotto"} — Cartaway`;
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
}

function renderProducts() {
  if (!elements.productGrid) return;

  let visibleProducts = state.products.filter((product) => product.available !== false);
  if (state.page === "home") {
    visibleProducts = visibleProducts.filter((product) => product.featured === true);
  } else {
    const normalizedSearch = normalizeText(state.search.trim());
    visibleProducts = visibleProducts
      .filter((product) => state.category === "tutte" || product.category === state.category)
      .filter((product) => {
        const searchable = normalizeText([product.name, product.category, product.unit, product.description].join(" "));
        return searchable.includes(normalizedSearch);
      });
  }

  if (state.sort === "price-asc") {
    visibleProducts.sort((first, second) => Number(first.price) - Number(second.price));
  } else if (state.sort === "price-desc") {
    visibleProducts.sort((first, second) => Number(second.price) - Number(first.price));
  } else {
    visibleProducts.sort((first, second) => Number(second.featured === true) - Number(first.featured === true));
  }

  if (elements.productCount) {
    elements.productCount.textContent = state.page === "home"
      ? `${visibleProducts.length} prodotti in evidenza`
      : `${visibleProducts.length} ${visibleProducts.length === 1 ? "prodotto" : "prodotti"}`;
  }
  elements.productGrid.innerHTML = visibleProducts.map(productCard).join("");
  if (elements.emptyState) elements.emptyState.hidden = visibleProducts.length > 0;
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
  const fullSubtotalCents = entries.reduce(
    (total, entry) => total + priceInCents(entry.product.price) * entry.quantity,
    0,
  );
  const subtotalCents = entries.reduce(
    (total, entry) => total + (recurring ? recurringPriceInCents(entry.product.price) : priceInCents(entry.product.price)) * entry.quantity,
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
  elements.cartItems.innerHTML = entries.map(({ product, quantity: itemQuantity }) => {
    const id = escapeHtml(product.id);
    const name = String(product.name || "Prodotto");
    const fullUnitPriceCents = priceInCents(product.price);
    const unitPriceCents = recurring ? recurringPriceInCents(product.price) : fullUnitPriceCents;
    const unitPrice = recurring && discountPercent > 0
      ? `<del>${escapeHtml(formatPrice(fullUnitPriceCents / 100))}</del> <strong>${escapeHtml(formatPrice(unitPriceCents / 100))}</strong>`
      : escapeHtml(formatPrice(unitPriceCents / 100));
    return `
      <article class="cart-item">
        <img class="cart-item__image" src="${escapeHtml(safeImageUrl(product.image))}" alt="" loading="lazy" />
        <div class="cart-item__details">
          <h3>${escapeHtml(name)}</h3>
          <p>${escapeHtml(product.unit || "")} · ${unitPrice}</p>
          <div class="quantity-control" aria-label="Quantità di ${escapeHtml(name)}">
            <button type="button" data-cart-change="-1" data-product-id="${id}" aria-label="Riduci ${escapeHtml(name)} di uno">−</button>
            <span>${itemQuantity}</span>
            <button type="button" data-cart-change="1" data-product-id="${id}" aria-label="Aumenta ${escapeHtml(name)} di uno">+</button>
          </div>
        </div>
        <strong class="cart-item__amount">${escapeHtml(formatPrice(unitPriceCents * itemQuantity / 100))}</strong>
      </article>
    `;
  }).join("");

  elements.cartEmpty.hidden = entries.length > 0;
  elements.cartSummary.hidden = entries.length === 0;
  elements.checkoutForm.hidden = entries.length === 0;
  elements.orderSubmit.disabled = entries.length === 0 || !minimumReached;
  elements.cartSubtotalLabel.textContent = recurring && discountPercent > 0 ? "Subtotale scontato" : "Subtotale articoli";
  elements.cartSubtotal.textContent = formatPrice(subtotalCents / 100);
  elements.cartDeliveryCost.textContent = deliveryQuote.label;
  elements.cartDeliveryCost.dataset.deliveryState = deliveryQuote.state;
  elements.cartDeliveryNote.textContent = deliveryQuote.note;
  elements.cartEstimatedTotal.textContent = deliveryQuote.costCents === null
    ? minimumReached ? "Da confermare" : "Minimo non raggiunto"
    : formatPrice((subtotalCents + deliveryQuote.costCents) / 100);
  elements.cartDiscountRow.hidden = !recurring || savingsCents <= 0;
  elements.cartDiscountAmount.textContent = `−${formatPrice(savingsCents / 100)}`;
  elements.cartCashbackAmount.textContent = formatPrice(techVoucherAmountCents(subtotalCents) / 100);
  if (elements.cartCashbackNote) {
    const voucherValidity = recurring
      ? `valido ${techVoucherValidityText(true)} dalla consegna grazie all'ordine ricorrente`
      : `valido ${techVoucherValidityText()} dalla consegna`;
    elements.cartCashbackNote.textContent = `Stima se è il primo ordine del mese: ${formatPercentage(techVoucherPercent())}% della spesa, fino a ${formatPrice(techVoucherMaximumCents() / 100)}, senza minimo. Un buono per cliente al mese, ${voucherValidity} e per un solo intervento. Non convertibile in denaro né cumulabile con altri buoni; idoneità da confermare su WhatsApp.`;
  }
  elements.cartCashback.hidden = entries.length === 0;

  if (!selectedTown) {
    elements.deliveryEstimate.textContent = "Seleziona il comune per stimare consegna e costo.";
  } else if (!deliveryZone) {
    elements.deliveryEstimate.textContent = "Verifichiamo copertura e costo per questo comune prima di confermare.";
  } else {
    const timing = [deliveryZone.delivery_time, deliveryZone.availability]
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .join(", ");
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

function addToCart(productId) {
  const product = state.products.find((item) => item.id === productId && item.available !== false);
  if (!product) return;
  state.cart[productId] = (state.cart[productId] || 0) + 1;
  saveCart();
  renderCart();
  showMessage(`${product.name} aggiunto al carrello.`);
}

function changeQuantity(productId, delta) {
  const nextQuantity = (state.cart[productId] || 0) + delta;
  if (nextQuantity < 1) {
    delete state.cart[productId];
  } else {
    state.cart[productId] = nextQuantity;
  }
  saveCart();
  renderCart();
}

function buildWhatsappUrl(message) {
  const number = String(state.site.whatsapp || "").replace(/\D/g, "");
  if (number.length < 8) return "";
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}

function renderSiteDetails() {
  const brand = String(state.site.brand || "Cartaway").trim();
  document.querySelectorAll("[data-brand]").forEach((element) => {
    element.textContent = brand;
  });
  document.title = state.page === "catalog"
    ? `Catalogo prodotti — ${brand}`
    : `${brand} — Carta per casa e ufficio, a Montoro`;

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
      ? `consegna a pagamento per ordini inferiori a ${formatPrice(thresholdCents / 100)}; costo da confermare su WhatsApp`
      : `consegna a pagamento: ${formatPrice(feeCents / 100)} per ordini inferiori a ${formatPrice(thresholdCents / 100)}`;
    return `${minimumDescription}${paidDescription}; gratuita da ${formatPrice(thresholdCents / 100)}.`;
  }
  if (zone.delivery_policy === "paid") {
    return feeCents === null
      ? "Consegna a pagamento, costo da confermare su WhatsApp."
      : `Consegna a pagamento: ${formatPrice(feeCents / 100)}.`;
  }
  return "Costo di consegna da confermare su WhatsApp.";
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
      ? "Consegna a pagamento; costo da confermare su WhatsApp."
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
      const details = [zone.delivery_time, zone.availability]
        .map((value) => String(value || "").trim())
        .filter(Boolean)
        .join(" · ");
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
      "Tempi indicativi, soggetti a disponibilità e indirizzo. La consegna viene concordata su WhatsApp.";
  }

  if (elements.deliveryNote) {
    elements.deliveryNote.textContent = state.site.delivery_note ||
      "Tempi indicativi, soggetti a disponibilità e indirizzo. La consegna viene concordata su WhatsApp.";
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
          <strong>${escapeHtml(zone.name || "Zona di consegna")}</strong>
          <span>${escapeHtml(zone.delivery_time || "Tempi da concordare")}</span>
          <small>${escapeHtml(locationText)}</small>
          <small>${escapeHtml(zone.availability || "Disponibilità da confermare")}</small>
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
        marker.bindPopup(`<strong>${escapeHtml(location.name)}</strong><br>${escapeHtml(zone.delivery_time || "Tempi da concordare")}<br>${escapeHtml(zone.availability || "Disponibilità da confermare")}<br>${escapeHtml(deliveryPolicyDescription(zone))}`);
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
      title: "Casa e ufficio, mai senza.",
      intro: "Carta igienica, rotoli cucina e tutto l'essenziale. Ordini in pochi passaggi, noi te li portiamo.",
      action: "Scegli i prodotti",
      actionHref: "catalogo.html",
      openPromo: false,
      deliveryHighlight: "Montoro: circa 2 ore",
      deliverySecondary: "Comuni vicini: in giornata, su conferma",
      caption: "UNA SCORTA IN MENO A CUI PENSARE",
    },
    {
      image: "https://images.unsplash.com/photo-1562240020-ce31ccb0fa7d?auto=format&fit=crop&w=2000&q=88",
      imageAlt: "Carta per stampante A4",
      eyebrow: "PROMO CASHBACK CARTAWAY",
      title: "Un Buono Tech per il tuo mese.",
      intro: "Sul primo ordine di carta e consumabili di ogni mese ricevi un Buono Tech pari al 50% della spesa, fino a 25 €. Nessuna spesa minima.",
      action: "Scopri la promo",
      actionHref: "#promo-dialog",
      openPromo: true,
      voucher: true,
      deliveryHighlight: "Un buono per cliente al mese",
      deliverySecondary: "60 giorni · 90 con ordine ricorrente · massimo 25 €",
      caption: "BUONO TECH · 50% DEL PRIMO ORDINE MENSILE",
    },
    {
      image: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=2000&q=88",
      imageAlt: "Scatole in magazzino, pronte per la consegna",
      eyebrow: "CONSEGNA LOCALE · ORDINI RICORRENTI",
      title: "La tua scorta, al ritmo giusto.",
      intro: "Scegli una consegna ogni 30 o 60 giorni: hai il 5% di sconto, prezzi bloccati per 12 mesi e puoi indicare un giorno fisso.",
      recurringVoucher: true,
      action: "Scopri le zone",
      actionHref: "#consegna",
      openPromo: false,
      deliveryHighlight: "Zona 01: gratuita, senza minimo",
      deliverySecondary: "Zona 02: 5 € sotto 30 €, gratuita da 30 € · Zona 03: spedizione a pagamento, 5 €",
      caption: "CONSEGNE PER ZONA · ORDINI OGNI 30 O 60 GIORNI",
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
    elements.heroImage.src = slide.image;
    elements.heroImage.alt = slide.imageAlt;
    elements.heroEyebrow.textContent = slide.eyebrow;
    elements.heroTitle.textContent = slide.title;
    elements.heroIntro.textContent = slide.voucher
      ? `Sul primo ordine di carta e consumabili di ogni mese ricevi un Buono Tech pari al ${formatPercentage(techVoucherPercent())}% della spesa, fino a ${formatPrice(techVoucherMaximumCents() / 100)}. Nessuna spesa minima.`
      : slide.recurringVoucher
        ? `${slide.intro} Con l'ordine ricorrente, la validità del Buono Tech si estende a ${techVoucherValidityText(true)} dalla consegna.`
        : slide.intro;
    elements.heroActionLabel.textContent = slide.action;
    elements.heroAction.href = slide.actionHref;
    elements.heroAction.dataset.openPromo = String(slide.openPromo);
    elements.heroDeliveryHighlight.textContent = slide.voucher
      ? `Un buono per cliente al mese · massimo ${formatPrice(techVoucherMaximumCents() / 100)}`
      : slide.deliveryHighlight;
    elements.heroDeliverySecondary.textContent = slide.voucher
      ? `${techVoucherValidityText()} dalla consegna · ${techVoucherValidityText(true)} con ordine ricorrente`
      : slide.deliverySecondary;
    elements.heroCaption.textContent = slide.voucher
      ? `BUONO TECH · ${formatPercentage(techVoucherPercent())}% DEL PRIMO ORDINE MENSILE`
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

  elements.categoryButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.category = button.dataset.category;
      elements.categoryButtons.forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      renderProducts();
    });
  });

  if (elements.productSearch) {
    elements.productSearch.addEventListener("input", (event) => {
      state.search = event.currentTarget.value;
      renderProducts();
    });
  }

  if (elements.productSort) {
    elements.productSort.addEventListener("change", (event) => {
      state.sort = event.currentTarget.value;
      renderProducts();
    });
  }

  elements.promoOpen.addEventListener("click", () => elements.promoDialog.showModal());
  elements.promoDialog.addEventListener("click", (event) => {
    if (event.target === elements.promoDialog) elements.promoDialog.close();
  });
  elements.promoDialog.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    elements.promoDialog.close();
  });

  elements.deliveryOpen.addEventListener("click", () => {
    elements.deliveryDialog.showModal();
    void initializeDeliveryMap();
  });
  elements.deliveryDialog.addEventListener("click", (event) => {
    if (event.target === elements.deliveryDialog) elements.deliveryDialog.close();
  });
  elements.deliveryDialogZones.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delivery-zone]");
    if (button) selectDeliveryZone(button.dataset.deliveryZone);
  });

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

  elements.cartItems.addEventListener("click", (event) => {
    const button = event.target.closest("[data-cart-change]");
    if (!button) return;
    changeQuantity(button.dataset.productId, Number(button.dataset.cartChange));
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
      window.location.assign("catalogo.html");
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

  elements.checkoutForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const items = cartEntries();
    if (!items.length) return;

    const formData = new FormData(elements.checkoutForm);
    const name = String(formData.get("name") || "").trim();
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
      (total, item) => total + priceInCents(item.product.price) * item.quantity,
      0,
    );
    const subtotalCents = items.reduce(
      (total, item) => total + (recurringOrder ? recurringPriceInCents(item.product.price) : priceInCents(item.product.price)) * item.quantity,
      0,
    );
    const savingsCents = fullSubtotalCents - subtotalCents;
    const deliveryZone = findDeliveryZoneForTown(town);
    const deliveryQuote = getDeliveryQuote(deliveryZone, subtotalCents, fullSubtotalCents);
    if (deliveryQuote.minimumReached === false) {
      showMessage(`Ordine minimo ${formatPrice(deliveryQuote.minimumOrderCents / 100)}: aggiungi altri prodotti per continuare.`);
      return;
    }
    const deliveryMessageLines = deliveryZone
      ? [
          `Zona di consegna: ${deliveryZone.id} (${deliveryZone.name}).`,
          `Regola: ${deliveryQuote.note}`,
          deliveryQuote.costCents === null
            ? `Costo consegna: ${deliveryQuote.label.toLocaleLowerCase("it-IT")}; importo da confermare.`
            : `Costo consegna: ${formatPrice(deliveryQuote.costCents / 100)}${deliveryQuote.costCents === 0 ? " (gratuita)" : ""}.`,
          deliveryQuote.costCents === null
            ? `Totale stimato: ${formatPrice(subtotalCents / 100)} + costo consegna da confermare.`
            : `Totale stimato, consegna inclusa: ${formatPrice((subtotalCents + deliveryQuote.costCents) / 100)}.`,
        ]
      : [
          `Zona di consegna da verificare per ${town}; costo da confermare su WhatsApp.`,
          `Totale articoli: ${formatPrice(subtotalCents / 100)}; totale finale da confermare.`,
        ];
    const itemLines = items.map(({ product, quantity }) => {
      const fullLineCents = priceInCents(product.price) * quantity;
      const unitPriceCents = recurringOrder ? recurringPriceInCents(product.price) : priceInCents(product.price);
      const lineTotalCents = unitPriceCents * quantity;
      const originalPrice = recurringOrder && discountPercent > 0
        ? ` (prezzo pieno ${formatPrice(fullLineCents / 100)})`
        : "";
      return `- ${quantity} x ${product.name} (${product.unit}) — ${formatPrice(lineTotalCents / 100)}${originalPrice}`;
    });
    const message = [
      `Buongiorno ${state.site.brand || "Cartaway"}, vorrei ordinare:`,
      "",
      ...itemLines,
      "",
      recurringOrder && savingsCents > 0 ? `Subtotale prima dello sconto: ${formatPrice(fullSubtotalCents / 100)}` : "",
      recurringOrder && savingsCents > 0 ? `Sconto ricorrente (${formatPercentage(discountPercent)}%): -${formatPrice(savingsCents / 100)}` : "",
      `Subtotale articoli${recurringOrder && discountPercent > 0 ? " scontato" : ""}: ${formatPrice(subtotalCents / 100)}`,
      `Buono Tech stimato, se è il primo ordine del mese: ${formatPrice(techVoucherAmountCents(subtotalCents) / 100)}.`,
      `Pari al ${formatPercentage(techVoucherPercent())}% della spesa, fino a ${formatPrice(techVoucherMaximumCents() / 100)}, senza minimo. Un solo buono per cliente al mese; valido ${techVoucherValidityText(recurringOrder)} dalla consegna${recurringOrder ? " grazie all'ordine ricorrente" : ""} e per un solo intervento. Non convertibile in denaro né cumulabile con altri buoni.`,
      ...deliveryMessageLines,
      "Disponibilità, pagamento e conferma ordine da concordare su WhatsApp.",
      "",
      name ? `Nome: ${name}` : "",
      `Telefono: ${phone}`,
      `Comune: ${town}`,
      `Indirizzo: ${address}`,
      preferredDate ? `Data preferita: ${new Date(`${preferredDate}T00:00:00`).toLocaleDateString("it-IT")}` : "",
      preferredTimeSlot ? `Fascia oraria preferita: ${preferredTimeSlot}` : "",
      recurringOrder ? `Frequenza richiesta: ogni ${recurringFrequency} giorni.` : "",
      recurringOrder && recurringDay ? `Giorno fisso del mese richiesto: ${recurringDay}.` : "",
      recurringOrder ? `Prezzo bloccato richiesto per ${priceLockMonths} mesi.` : "",
      recurringOrder ? "Ricorrenza e giorno di consegna da confermare su WhatsApp; il sito non attiva rinnovi automatici." : "",
      notes ? `Note: ${notes}` : "",
      "",
      "Potete confermare disponibilità, data, fascia oraria e modalità di pagamento?",
    ].filter(Boolean).join("\n");
    const url = buildWhatsappUrl(message);
    if (!url) {
      showMessage("Il numero WhatsApp non è configurato. Contattaci dai recapiti in fondo alla pagina.");
      return;
    }
    window.location.assign(url);
  });
}

async function initializeShop() {
  setupEvents();
  renderCart();

  try {
    const [siteResponse, productsResponse] = await Promise.all([
      fetch("data/site.json"),
      fetch("data/products.json"),
    ]);
    if (!siteResponse.ok || !productsResponse.ok) throw new Error("Impossibile caricare i dati del negozio.");

    const [site, catalog] = await Promise.all([siteResponse.json(), productsResponse.json()]);
    state.site = site;
    configureTechVoucher();
    configureRecurringOrder();
    updateRecurringControls();
    state.products = Array.isArray(catalog.products) ? catalog.products : [];
    state.cart = Object.fromEntries(
      Object.entries(state.cart).filter(([id]) =>
        state.products.some((product) => product.id === id && product.available !== false),
      ),
    );
    saveCart();
    renderSiteDetails();
    if (elements.deliveryDialog.open) void initializeDeliveryMap();
    renderProducts();
    renderProductDetail();
    renderCart();
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
