---
name: analyze-website
description: "Deep analysis of a company's website to detect payment capabilities, technology stack, business model, and current payment processor."
---
# Analyze Website

Deep analysis of a company's website to detect payment capabilities, technology stack, business model, and current payment processor.

## Arguments

- `$0` (required): Company domain (e.g. "totalpass.com.mx")

## Steps

1. **Fetch the main page** using `http_request` with method GET on `https://{domain}`. Analyze the HTML for:
   - Navigation links to checkout, pricing, plans, subscriptions, or payment pages
   - Footer links to terms of service, payment policies
   - Evidence of ecommerce (product listings, cart, buy buttons)

2. **Fetch key subpages** if found in step 1. Common paths to check:
   - `/pricing`, `/precios`, `/planes`
   - `/checkout`, `/pago`
   - `/subscribe`, `/suscripcion`
   - `/tienda`, `/shop`, `/store`
   Only fetch pages that exist — do not waste requests on 404s.

3. **Detect payment processor** by examining HTML and JavaScript sources:
   - Look for script tags: `js.stripe.com`, `sdk.mercadopago.com`, `checkout.adyen.com`, `paypal.com/sdk`, `cdn.openpay.mx`
   - Look for iframes pointing to payment providers
   - Look for form actions or API endpoints mentioning payment providers
   - Look for logos or brand mentions of: MercadoPago, Stripe, Adyen, PayPal, Openpay, Clip, Yuno, DLocal

4. **Identify technology stack:**
   - Shopify: look for `cdn.shopify.com`, `myshopify.com`
   - Magento: look for `mage/`, `Magento_`, `magento.com`
   - WooCommerce: look for `woocommerce`, `wp-content`
   - VTEX: look for `vtex.com`, `vteximg`
   - Custom: if no known platform is detected

5. **Determine business model** based on the website content:
   - Subscription platform (recurring billing, plans, membership)
   - Ecommerce retailer (product catalog, cart, checkout)
   - Marketplace (multiple sellers, commission model)
   - SaaS / Software (software product, pricing tiers)
   - Education platform (courses, tuition, enrollment)
   - Healthcare services (appointments, consultations)
   - Professional services (consulting, booking)
   - Ticketing (events, concerts, experiences)

6. **Estimate payment volume** using available signals:
   - Large product catalog → higher volume
   - Subscription model with visible user counts → estimate recurring revenue
   - Brand presence and market position → proxy for transaction volume
   - Company employee count → correlates with revenue
   - Classify as: "Likely above $1.5M MXN/month", "Possibly above $1.5M MXN/month", or "Unlikely to meet threshold"

7. **Report findings** in a structured format with all detected information.

## Important Notes

- Be efficient with HTTP requests — don't fetch more than 5 pages per company.
- Some sites may block automated requests. If you get a 403 or captcha, note it and move on with available information.
- Focus on evidence, not assumptions. If you can't detect something, say "Not detected" rather than guessing.
