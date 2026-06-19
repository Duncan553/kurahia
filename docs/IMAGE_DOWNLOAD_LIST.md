# Image Download List — Waterfront Country Club

Download these from waterfrontcountryclub.com and place in the paths below.
The frontend already references these paths — drop the photos in and they appear.

## Resort Background (DONE)
- ✅ `employee_pwa/public/images/resort-bg.jpg` — DJI_0669-scaled.jpg (already downloaded)
- ✅ `owner_pwa/public/images/resort-bg.jpg` — same file (already downloaded)

## Villas → `employee_pwa/public/images/villas/`
- villa-1.jpg — Villa 1 (KSh 100,000/night, 8,000 ft²)
- villa-2.jpg — Villa 2 (KSh 100,000/night)
- villa-4.jpg — Villa 4 (KSh 120,000/night)
- villa-6.jpg — Villa 6 (KSh 140,000/night, 8,000 ft²)
- villa-14.jpg — Villa 14 (KSh 65,000/night, 1,200 ft²)
- villa-15.jpg — Villa 15 (KSh 65,000/night, 1,200 ft²)

## Spa & Wellness → `employee_pwa/public/images/spa/`
- spa-1.jpg — Massage room / treatment area
- spa-2.jpg — Aromatherapy / beauty
- gym-1.jpg — Gym / personal training area

## Pool → `employee_pwa/public/images/pool/`
- pool-1.jpg — Swimming pool aerial or ground view

## Dining → `employee_pwa/public/images/dining/`
- restaurant-1.jpg — Top Restaurant interior or terrace
- dining-2.jpg — Food / grills / seafood spread

## Water Activities → `employee_pwa/public/images/water/`
- boats-1.jpg — Boat rides / sunset cruise
- jetski-1.jpg — Jet ski on the dam
- kayaking-1.jpg — Kayaking
- fishing-1.jpg — Fishing with gear

## Weddings → `employee_pwa/public/images/weddings/`
- grounds-1.jpg — Wedding grounds / event field

## Ambience → `employee_pwa/public/images/ambience/`
- nature-1.jpg — Nature trails
- golf-cart-1.jpg — Golf cart rides

## Logo
- `employee_pwa/public/images/logo.png` — Main logo
- `employee_pwa/public/images/logo-white.png` — White variant for dark backgrounds

## Menu Items → `employee_pwa/public/images/menu/`
- Photos per menu item. Manager uploads via the menu edit screen (PATCH /menu/items/:id with image_path).
- Until uploaded, items show a placeholder icon.

## How to Add
1. Download from the resort website or take new photos
2. Resize to ~1200px wide max, JPEG quality 80 (keeps file size reasonable)
3. Drop into the correct folder above
4. The PWA service worker will precache them on next build
