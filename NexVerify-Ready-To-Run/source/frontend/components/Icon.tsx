// Small line icons; the SVG paths are fixed strings from lib/copy.ts (never user input).
export function Icon({ svg, className = "ic" }: { svg: string; className?: string }) {
  return <svg className={className} viewBox="0 0 32 32" aria-hidden="true" dangerouslySetInnerHTML={{ __html: svg }} />;
}

export function Html({ html, as: Tag = "span" }: { html: string; as?: "span" | "li" | "div" }) {
  return <Tag dangerouslySetInnerHTML={{ __html: html }} />;
}
