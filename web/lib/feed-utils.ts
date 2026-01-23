export interface FeedMetaSuggestion {
  identifier: string;
  name: string;
}

const DEFAULT_IDENTIFIER = 'feed';
const DEFAULT_NAME = 'Feed';

const stripExtension = (value: string) => value.replace(/\.[^/.]+$/, '');

const slugify = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');

const titleize = (value: string) =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());

export const suggestFeedMeta = (
  filename?: string | null,
  sheet?: string | null
): FeedMetaSuggestion => {
  const base = filename ? stripExtension(filename) : DEFAULT_NAME;
  const baseTitle = titleize(base) || DEFAULT_NAME;
  const sheetLabel = sheet?.trim() || '';
  const sheetSlug = slugify(sheetLabel);

  let identifier = slugify(base) || DEFAULT_IDENTIFIER;
  if (identifier.length < 3) {
    identifier = sheetSlug ? `feed_${sheetSlug}` : `feed_${Date.now()}`;
  }
  if (sheetSlug && !identifier.includes(sheetSlug)) {
    identifier = `${identifier}_${sheetSlug}`;
  }

  let name = baseTitle;
  if (sheetLabel && !baseTitle.toLowerCase().includes(sheetLabel.toLowerCase())) {
    name = `${baseTitle} · ${sheetLabel}`;
  }

  return { identifier, name };
};
