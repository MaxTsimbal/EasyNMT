# EasyNMT SEO та Google Search Console

## Що вже додано у v0.9.4

- SEO title та meta description для головної сторінки.
- Пошукові фрази EasyNMT і «Легкий НМТ» у видимому тексті.
- canonical URL, Open Graph і Twitter metadata.
- structured data WebApplication.
- /robots.txt і /sitemap.xml.
- Приватні сторінки за замовчуванням мають noindex.
- Підтримка Google Search Console verification через змінну GOOGLE_SITE_VERIFICATION.

## Після деплою

1. Відкрий https://easynmt.up.railway.app/robots.txt
2. Відкрий https://easynmt.up.railway.app/sitemap.xml
3. У Google Search Console додай URL-prefix property:
   https://easynmt.up.railway.app/
4. Обери HTML tag verification і скопіюй тільки значення content.
5. У Railway Variables створи:
   GOOGLE_SITE_VERIFICATION=<значення content>
6. Після redeploy натисни Verify у Search Console.
7. У розділі Sitemaps надішли:
   sitemap.xml
8. Через URL Inspection встав головну URL і натисни Request indexing.

Індексація не миттєва. Google сам вирішує час сканування та позицію сторінки.
