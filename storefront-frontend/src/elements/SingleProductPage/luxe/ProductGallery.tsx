'use client';

import Image from 'next/image';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { ChevronLeftIcon, ChevronRightIcon, CloseIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { mediaUrl } from '@/lib/media';
import type { ProductImageStorefront } from '@/types/catalogue';

import styles from './ProductGallery.module.css';

interface Props {
  images: ProductImageStorefront[];
  productName: string;
}

/**
 * Keeps a horizontal scroll-snap track and an index in step: scrolling or
 * swiping the track updates the index, and `go()` scrolls the track.
 */
function useSlideTrack(count: number) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);

  const go = useCallback(
    (next: number, behavior: ScrollBehavior = 'smooth') => {
      const track = trackRef.current;
      const target = (next + count) % count;
      setIndex(target);
      track?.scrollTo({ left: target * track.clientWidth, behavior });
    },
    [count],
  );

  const onScroll = useCallback(() => {
    const track = trackRef.current;
    if (!track || track.clientWidth === 0) return;
    setIndex(Math.round(track.scrollLeft / track.clientWidth));
  }, []);

  return { trackRef, index, go, onScroll };
}

/**
 * Product image viewer: a two-column thumbnail grid beside a 3:4 main image
 * (a swipeable strip with dots on phones). Clicking the main image opens a
 * full-screen viewer with arrows, a thumbnail rail and dots; Esc, the arrow
 * keys, the close button or a click on the image dismiss/navigate it.
 *
 * The catalogue carries images only -- no product video -- so there is no
 * video slide.
 */
export default function ProductGallery({ images, productName }: Props) {
  const main = useSlideTrack(images.length);
  const [viewerOpen, setViewerOpen] = useState(false);

  if (images.length === 0) {
    return (
      <div className={styles.gallery}>
        <div className={`${styles.main} ${styles.empty}`}>No image yet</div>
      </div>
    );
  }

  const multiple = images.length > 1;

  return (
    <div className={styles.gallery}>
      {multiple && (
        <div className={styles.thumbs} role="tablist" aria-label="Product images">
          {images.map((image, i) => (
            <button
              key={image.id}
              type="button"
              role="tab"
              aria-selected={main.index === i}
              aria-label={`View image ${i + 1}`}
              className={`${styles.thumb} ${main.index === i ? styles.thumbActive : ''}`}
              onClick={() => main.go(i)}
            >
              <Image src={mediaUrl(image.url)} alt="" fill sizes="64px" className={styles.cover} />
            </button>
          ))}
        </div>
      )}

      <div className={styles.mainWrap}>
        <div
          ref={main.trackRef}
          className={styles.main}
          onScroll={main.onScroll}
          tabIndex={0}
          aria-roledescription="carousel"
          aria-label={`${productName} images`}
          onKeyDown={event => {
            if (event.key === 'ArrowRight') main.go(main.index + 1);
            if (event.key === 'ArrowLeft') main.go(main.index - 1);
            if (event.key === 'Enter') setViewerOpen(true);
          }}
        >
          {images.map((image, i) => (
            <button
              key={image.id}
              type="button"
              className={styles.slide}
              onClick={() => setViewerOpen(true)}
              aria-label={`Enlarge image ${i + 1} of ${images.length}`}
              tabIndex={-1}
            >
              <Image
                src={mediaUrl(image.url)}
                alt={image.alt_text ?? productName}
                fill
                priority={i === 0}
                sizes="(max-width: 899px) 100vw, 45vw"
                className={styles.cover}
              />
            </button>
          ))}
        </div>

        {multiple && (
          <>
            <button
              type="button"
              className={`${styles.arrow} ${styles.arrowPrev}`}
              onClick={() => main.go(main.index - 1)}
              aria-label="Previous image"
            >
              <ChevronLeftIcon size={18} />
            </button>
            <button
              type="button"
              className={`${styles.arrow} ${styles.arrowNext}`}
              onClick={() => main.go(main.index + 1)}
              aria-label="Next image"
            >
              <ChevronRightIcon size={18} />
            </button>
            <div className={styles.dots} aria-hidden="true">
              {images.map((image, i) => (
                <span key={image.id} className={`${styles.dot} ${main.index === i ? styles.dotActive : ''}`} />
              ))}
            </div>
          </>
        )}
      </div>

      {viewerOpen && (
        <ImageViewer
          images={images}
          productName={productName}
          startIndex={main.index}
          onClose={index => {
            setViewerOpen(false);
            main.go(index, 'auto');
          }}
        />
      )}
    </div>
  );
}

function ImageViewer({
  images,
  productName,
  startIndex,
  onClose,
}: Props & { startIndex: number; onClose: (index: number) => void }) {
  const viewer = useSlideTrack(images.length);
  const closeRef = useRef<HTMLButtonElement>(null);
  const { go, index } = viewer;

  // Open on the image that was showing, without animating there.
  useEffect(() => {
    go(startIndex, 'auto');
    closeRef.current?.focus();
  }, [go, startIndex]);

  useEffect(() => {
    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose(index);
      if (event.key === 'ArrowRight') go(index + 1);
      if (event.key === 'ArrowLeft') go(index - 1);
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [go, index, onClose]);

  const multiple = images.length > 1;

  // Portalled to <body> so no sticky/positioned ancestor can stack above it.
  return createPortal(
    <div className={styles.viewer} role="dialog" aria-modal="true" aria-label={`${productName} image viewer`}>
      <div ref={viewer.trackRef} className={styles.viewerTrack} onScroll={viewer.onScroll}>
        {images.map((image, i) => (
          <div key={image.id} className={styles.viewerSlide}>
            <button
              type="button"
              className={styles.viewerImage}
              onClick={() => onClose(index)}
              aria-label="Close image viewer"
              tabIndex={-1}
            >
              <Image
                src={mediaUrl(image.url)}
                alt={image.alt_text ?? `${productName}, image ${i + 1}`}
                fill
                sizes="(max-width: 899px) 100vw, 75vh"
                className={styles.contain}
              />
            </button>
          </div>
        ))}
      </div>

      <button ref={closeRef} type="button" className={styles.viewerClose} onClick={() => onClose(index)} aria-label="Close">
        <CloseIcon size={30} />
      </button>

      {multiple && (
        <>
          <button
            type="button"
            className={`${styles.viewerArrow} ${styles.viewerPrev}`}
            onClick={() => go(index - 1)}
            aria-label="Previous image"
          >
            <ChevronLeftIcon size={32} />
          </button>
          <button
            type="button"
            className={`${styles.viewerArrow} ${styles.viewerNext}`}
            onClick={() => go(index + 1)}
            aria-label="Next image"
          >
            <ChevronRightIcon size={32} />
          </button>

          <div className={styles.viewerRail}>
            {images.map((image, i) => (
              <button
                key={image.id}
                type="button"
                className={`${styles.viewerThumb} ${index === i ? styles.viewerThumbActive : ''}`}
                onClick={() => go(i)}
                aria-label={`View image ${i + 1}`}
                aria-current={index === i}
              >
                <Image src={mediaUrl(image.url)} alt="" fill sizes="60px" className={styles.cover} />
              </button>
            ))}
          </div>

          <div className={styles.viewerDots} aria-hidden="true">
            {images.map((image, i) => (
              <span key={image.id} className={`${styles.viewerDot} ${index === i ? styles.viewerDotActive : ''}`} />
            ))}
          </div>
        </>
      )}
    </div>,
    document.body,
  );
}
