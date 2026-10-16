/* Apprentix — "Follow a country": copy a country's feed link to the clipboard.
   Without JavaScript the plain feed link is still there. */

for (const btn of document.querySelectorAll('.follow-copy[data-feed]')) {
  const label = btn.textContent;
  btn.hidden = false;
  btn.addEventListener('click', async () => {
    let ok = false;
    try { await navigator.clipboard.writeText(btn.dataset.feed); ok = true; } catch { /* clipboard blocked */ }
    btn.textContent = ok ? 'Feed link copied ✓ — paste it into your feed reader' : btn.dataset.feed;
    setTimeout(() => { btn.textContent = label; }, ok ? 2600 : 8000);
  });
}
