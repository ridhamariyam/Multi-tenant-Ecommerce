/**
 * The runway's looks.
 *
 * The backend has no "look" entity, so a look is curated here: a model
 * cut-out plus up to three catalogue products, referenced by slug. Product
 * names, prices, options and stock are read live from
 * `/storefront/products/by-slug/:slug`; a slug that does not resolve is
 * skipped, so a deleted product never breaks the page.
 *
 * `pin` is where that piece's numbered dot sits on the model, as
 * [left %, top %] of the figure box. `tag` shows a small swing tag ("New").
 */

export interface RunwayPieceConfig {
  slug: string;
  pin?: [number, number];
  tag?: string;
}

export interface RunwayLookConfig {
  name: string;
  /** Transparent-background full-body cut-out, ~9:16. */
  model: { src: string; srcLarge: string };
  pieces: RunwayPieceConfig[];
}

const ASSETS = 'https://reel-ref-try-the-look.vercel.app/assets/';
const model = (n: number) => ({ src: `${ASSETS}model-${n}-640.webp`, srcLarge: `${ASSETS}original-look-${n}.webp` });

/** Default pin spots for pieces 1–3: top, middle, lower. */
export const DEFAULT_PINS: [number, number][] = [
  [50, 28],
  [48, 58],
  [45, 88],
];

/*
 * Dummy CliQ. catalogue (backend/app/commands/seed_cliq_demo.py). Swap the
 * slugs as real products are added, e.g. { slug: 'boxy-tee', tag: 'New' }.
 * Pins: outer layer on the chest, tee at the collar, shoes at the feet.
 */
const LAYER: [number, number] = [50, 36];
const TEE: [number, number] = [47, 21];
const SHOES: [number, number] = [45, 95];

export const RUNWAY_LOOKS: RunwayLookConfig[] = [
  {
    name: 'The City Edit',
    model: model(1),
    pieces: [{ slug: 'sand-crew-sweatshirt', pin: LAYER }, { slug: 'reign-graphic-tee', pin: TEE }, { slug: 'dune-low-sneaker', pin: SHOES }],
  },
  {
    name: 'Gallery Opening',
    model: model(5),
    pieces: [{ slug: 'star-graphic-hoodie', pin: LAYER, tag: 'New' }, { slug: 'reign-graphic-tee', pin: TEE }, { slug: 'court-classic-sneaker', pin: SHOES }],
  },
  {
    name: 'Gallery Opening',
    model: model(4),
    pieces: [{ slug: 'varsity-hoodie', pin: LAYER }, { slug: 'reign-graphic-tee', pin: TEE }, { slug: 'court-classic-sneaker', pin: SHOES, tag: 'New' }],
  },
  {
    name: 'Studio Day',
    model: model(6),
    pieces: [{ slug: 'star-graphic-hoodie', pin: LAYER }, { slug: 'reign-graphic-tee', pin: TEE }, { slug: 'dune-low-sneaker', pin: SHOES }],
  },
  {
    name: 'Studio Day',
    model: model(3),
    pieces: [{ slug: 'sand-crew-sweatshirt', pin: LAYER }, { slug: 'reign-graphic-tee', pin: TEE }, { slug: 'court-classic-sneaker', pin: SHOES }],
  },
  {
    name: 'Studio Day',
    model: model(2),
    pieces: [{ slug: 'statement-hoodie', pin: LAYER }, { slug: 'reign-graphic-tee', pin: TEE }, { slug: 'noir-leather-sneaker', pin: SHOES }],
  },
];

export const RUNWAY_COPY = {
  title: 'Try the Look.',
  subtitle: 'Six looks, styled head to toe. Tap a pin to see the piece.',
};
