export const $ = (s) => document.querySelector(s);
export const plainText = value => String(value ?? '').replace(/<br\s*\/?>/gi, ' · ').replace(/<[^>]*>/g, '');
export function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
export function button(text, onClick, cls = 'text-button') {
  const node = el('button', text, cls);
  node.type = 'button'; node.onclick = onClick;
  return node;
}
