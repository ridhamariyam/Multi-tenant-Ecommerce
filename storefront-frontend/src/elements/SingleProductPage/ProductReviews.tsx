'use client';

import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { type FormEvent, useActionState, useEffect, useId, useRef, useState } from 'react';

import { useSignInModal } from '@/context/SignInModalContext';
import { formatDate } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import { createReview, deleteReview, refreshProductReviews } from '@/lib/reviews/actions';
import { MAX_IMAGES_PER_REVIEW, MAX_RATING, type RatingSummary, type Review, type ReviewImage } from '@/types/reviews';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import styles from './luxe/Reviews.module.css';

/** Mirror the backend limits so problems surface before anything is sent. */
const MAX_TITLE = 150;
const MAX_COMMENT = 2000;
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const initialDeleteState = { status: 'idle' as const, message: null as string | null };

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.4">
      <path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z" strokeLinejoin="round" />
    </svg>
  );
}

function Stars({ value, label }: { value: number; label?: string }) {
  return (
    <span className={styles.stars} role="img" aria-label={label ?? `${value} out of ${MAX_RATING} stars`}>
      {Array.from({ length: MAX_RATING }).map((_, index) => (
        <StarIcon key={index} filled={index < value} />
      ))}
    </span>
  );
}

/* --------------------------------- Form ---------------------------------- */

interface PendingPhoto {
  key: string;
  file: File;
  preview: string;
  status: 'ready' | 'uploading' | 'uploaded' | 'failed';
  error?: string;
}

interface FieldErrors {
  rating?: string;
  title?: string;
  comment?: string;
  photos?: string;
}

function photoProblem(file: File): string | null {
  if (!PHOTO_TYPES.includes(file.type)) return `${file.name}: photos must be JPEG, PNG or WebP.`;
  if (file.size > MAX_PHOTO_BYTES) return `${file.name}: each photo must be 5 MB or smaller.`;
  return null;
}

async function uploadPhoto(reviewId: string, photo: PendingPhoto, alt: string): Promise<{ image?: ReviewImage; error?: string }> {
  const body = new FormData();
  body.set('file', photo.file, photo.file.name);
  body.set('alt_text', alt);
  try {
    const response = await fetch(`/reviews/${reviewId}/photos`, { method: 'POST', body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) return { error: payload.message ?? 'Upload failed.' };
    return { image: payload.image };
  } catch {
    return { error: 'Could not reach CliQ. Check your connection.' };
  }
}

/**
 * The review form.
 *
 * Every value lives in React state and the form submits through `onSubmit`,
 * not a form action: React 19 resets a form after its action runs, which is
 * what used to wipe the text whenever the server rejected a missing rating.
 * Nothing here is cleared until the review and all its photos are saved.
 *
 * A review is created first and its photos uploaded after, one request each.
 * If a photo fails, the created review's id is kept so a retry only re-sends
 * the photos that are still outstanding -- re-creating the review would be
 * rejected as a duplicate.
 */
function WriteReviewForm({ productId, productName }: { productId: string; productName: string }) {
  const router = useRouter();
  const baseId = useId();
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [title, setTitle] = useState('');
  const [comment, setComment] = useState('');
  const [photos, setPhotos] = useState<PendingPhoto[]>([]);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const busyRef = useRef(false);
  const ratingRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const commentRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const previewsRef = useRef<string[]>([]);

  // Object URLs are revoked when a photo is removed and when the form goes away.
  useEffect(() => () => previewsRef.current.forEach(url => URL.revokeObjectURL(url)), []);

  const locked = reviewId !== null; // the review exists; only its photos are outstanding

  function addPhotos(files: FileList | null) {
    if (!files?.length) return;
    const room = MAX_IMAGES_PER_REVIEW - photos.length;
    const problems: string[] = [];
    const accepted: PendingPhoto[] = [];
    for (const file of Array.from(files)) {
      const problem = photoProblem(file);
      if (problem) problems.push(problem);
      else if (accepted.length >= room) problems.push(`You can add up to ${MAX_IMAGES_PER_REVIEW} photos.`);
      else {
        const preview = URL.createObjectURL(file);
        previewsRef.current.push(preview);
        accepted.push({ key: `${file.name}-${file.size}-${preview}`, file, preview, status: 'ready' });
      }
    }
    setPhotos(current => [...current, ...accepted]);
    setErrors(current => ({ ...current, photos: problems.length ? [...new Set(problems)].join(' ') : undefined }));
    if (fileRef.current) fileRef.current.value = '';
  }

  function removePhoto(key: string) {
    setPhotos(current => {
      const photo = current.find(p => p.key === key);
      if (photo) URL.revokeObjectURL(photo.preview);
      return current.filter(p => p.key !== key);
    });
  }

  function validate(): FieldErrors {
    const next: FieldErrors = {};
    if (!locked) {
      if (rating < 1 || rating > MAX_RATING) next.rating = 'Please select a star rating';
      if (title.trim().length > MAX_TITLE) next.title = `Keep the title under ${MAX_TITLE} characters`;
      if (comment.trim().length > MAX_COMMENT) next.comment = `Keep the review under ${MAX_COMMENT} characters`;
    }
    if (photos.length > MAX_IMAGES_PER_REVIEW) next.photos = `You can add up to ${MAX_IMAGES_PER_REVIEW} photos.`;
    const bad = photos.find(p => photoProblem(p.file));
    if (bad) next.photos = photoProblem(bad.file) ?? undefined;
    return next;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busyRef.current) return; // one request in flight at a time

    const found = validate();
    setErrors(found);
    setFormError(null);
    if (Object.values(found).some(Boolean)) {
      if (found.rating) ratingRef.current?.focus();
      else if (found.title) titleRef.current?.focus();
      else if (found.comment) commentRef.current?.focus();
      else if (found.photos) fileRef.current?.focus();
      return;
    }

    busyRef.current = true;
    setBusy(true);
    try {
      let id = reviewId;
      if (!id) {
        const result = await createReview({ productId, rating, title, comment });
        if (result.status === 'error') {
          setErrors({
            rating: result.fieldErrors?.rating,
            title: result.fieldErrors?.title,
            comment: result.fieldErrors?.comment,
          });
          setFormError(result.message);
          return;
        }
        id = result.reviewId;
        setReviewId(id);
      }

      let failed = 0;
      for (const photo of photos) {
        if (photo.status === 'uploaded') continue;
        setPhotos(current => current.map(p => (p.key === photo.key ? { ...p, status: 'uploading', error: undefined } : p)));
        const { error } = await uploadPhoto(id, photo, `Customer photo of ${productName}`);
        if (error) failed += 1;
        setPhotos(current =>
          current.map(p => (p.key === photo.key ? { ...p, status: error ? 'failed' : 'uploaded', error } : p)),
        );
      }

      if (failed > 0) {
        setFormError(
          `Your review is saved, but ${failed} photo${failed === 1 ? '' : 's'} could not be uploaded. ` +
            'Retry, or remove the photo to finish without it.',
        );
        return;
      }

      await refreshProductReviews(productId);
      previewsRef.current.forEach(url => URL.revokeObjectURL(url));
      previewsRef.current = [];
      setRating(0);
      setTitle('');
      setComment('');
      setPhotos([]);
      setReviewId(null);
      setDone(true);
      router.refresh();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  if (done) {
    return (
      <p className={styles.notice} role="status">
        Thank you — your review has been posted.
      </p>
    );
  }

  const outstanding = photos.filter(p => p.status !== 'uploaded').length;
  const submitLabel = busy
    ? locked
      ? 'Uploading photos…'
      : 'Submitting…'
    : locked
      ? outstanding > 0
        ? 'Retry photo upload'
        : 'Finish'
      : 'Submit review';

  const shown = hover || rating;

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate aria-busy={busy}>
      <fieldset className={styles.field} disabled={locked}>
        <legend className={styles.label}>Your rating</legend>
        <div
          className={styles.starPicker}
          role="radiogroup"
          aria-label="Rating"
          aria-describedby={errors.rating ? `${baseId}-rating-error` : undefined}
          onMouseLeave={() => setHover(0)}>
          {Array.from({ length: MAX_RATING }).map((_, index) => {
            const star = index + 1;
            return (
              <button
                key={star}
                ref={star === 1 ? ratingRef : undefined}
                type="button"
                role="radio"
                aria-checked={rating === star}
                aria-label={`${star} star${star === 1 ? '' : 's'}`}
                className={styles.starButton}
                onMouseEnter={() => setHover(star)}
                onFocus={() => setHover(0)}
                onClick={() => {
                  setRating(star);
                  setErrors(current => ({ ...current, rating: undefined }));
                }}>
                <StarIcon filled={star <= shown} />
              </button>
            );
          })}
        </div>
        {errors.rating && (
          <p id={`${baseId}-rating-error`} className={styles.error} role="alert">
            {errors.rating}
          </p>
        )}
      </fieldset>

      <div className={styles.field}>
        <label htmlFor={`${baseId}-title`} className={styles.label}>
          Title <span className={styles.hint}>(optional)</span>
        </label>
        <input
          ref={titleRef}
          id={`${baseId}-title`}
          type="text"
          value={title}
          maxLength={MAX_TITLE}
          disabled={locked}
          onChange={event => setTitle(event.target.value)}
          aria-invalid={!!errors.title}
          className={`${styles.input} ${errors.title ? styles.invalid : ''}`}
        />
        {errors.title && <p className={styles.error}>{errors.title}</p>}
      </div>

      <div className={styles.field}>
        <label htmlFor={`${baseId}-comment`} className={styles.label}>
          Your review <span className={styles.hint}>(optional)</span>
        </label>
        <textarea
          ref={commentRef}
          id={`${baseId}-comment`}
          value={comment}
          maxLength={MAX_COMMENT}
          rows={5}
          disabled={locked}
          placeholder="Tell others about the fit, fabric and finish"
          onChange={event => setComment(event.target.value)}
          aria-invalid={!!errors.comment}
          className={`${styles.textarea} ${errors.comment ? styles.invalid : ''}`}
        />
        <p className={styles.counter}>
          {comment.length}/{MAX_COMMENT}
        </p>
        {errors.comment && <p className={styles.error}>{errors.comment}</p>}
      </div>

      <div className={styles.field}>
        <span className={styles.label} id={`${baseId}-photos`}>
          Photos <span className={styles.hint}>(optional, up to {MAX_IMAGES_PER_REVIEW} · JPEG, PNG or WebP · 5 MB each)</span>
        </span>
        <ul className={styles.photoGrid} aria-labelledby={`${baseId}-photos`}>
          {photos.map(photo => (
            <li
              key={photo.key}
              className={`${styles.photoItem} ${photo.status === 'uploading' ? styles.photoUploading : ''} ${
                photo.status === 'failed' ? styles.photoFailed : ''
              }`}>
              {/* eslint-disable-next-line @next/next/no-img-element -- a local object URL preview */}
              <img src={photo.preview} alt={`Selected photo ${photo.file.name}`} />
              {photo.status !== 'ready' && (
                <span className={styles.photoBadge}>
                  {photo.status === 'uploading' ? 'Uploading' : photo.status === 'uploaded' ? 'Added' : 'Failed'}
                </span>
              )}
              {photo.status !== 'uploaded' && (
                <button
                  type="button"
                  className={styles.removePhoto}
                  disabled={busy}
                  aria-label={`Remove ${photo.file.name}`}
                  onClick={() => removePhoto(photo.key)}>
                  <svg width="10" height="10" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
                    <path d="M6 6l12 12M18 6 6 18" />
                  </svg>
                </button>
              )}
            </li>
          ))}
          {photos.length < MAX_IMAGES_PER_REVIEW && (
            <li>
              <label className={styles.addPhoto}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                Add
                <input
                  ref={fileRef}
                  type="file"
                  accept={PHOTO_TYPES.join(',')}
                  multiple
                  disabled={busy}
                  className={styles.visuallyHidden}
                  aria-describedby={errors.photos ? `${baseId}-photos-error` : undefined}
                  onChange={event => addPhotos(event.target.files)}
                />
              </label>
            </li>
          )}
        </ul>
        {errors.photos && (
          <p id={`${baseId}-photos-error`} className={styles.error} role="alert">
            {errors.photos}
          </p>
        )}
      </div>

      {locked && !formError && <p className={styles.notice}>Your review is saved. Finish to add your photos.</p>}
      {formError && (
        <p className={`${styles.notice} ${styles.noticeError}`} role="alert">
          {formError}
        </p>
      )}

      <button type="submit" disabled={busy} className={styles.submit}>
        {submitLabel}
      </button>
    </form>
  );
}

/* --------------------------------- List ---------------------------------- */

function DeleteReviewButton({ reviewId, productId }: { reviewId: string; productId: string }) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(deleteReview, initialDeleteState);

  useEffect(() => {
    if (state.status === 'success') router.refresh();
  }, [state, router]);

  return (
    <form action={formAction}>
      <input type="hidden" name="review_id" value={reviewId} />
      <input type="hidden" name="product_id" value={productId} />
      <button type="submit" disabled={pending} className={styles.deleteButton}>
        {pending ? 'Deleting…' : 'Delete your review'}
      </button>
    </form>
  );
}

function Summary({ summary }: { summary: RatingSummary }) {
  const total = summary.total_reviews;
  return (
    <div className={styles.summary}>
      <span className={styles.average}>{summary.average_rating.toFixed(1)}</span>
      <span className={styles.summaryMeta}>
        <Stars value={Math.round(summary.average_rating)} label={`Average ${summary.average_rating.toFixed(1)} out of 5`} />
        {total} {total === 1 ? 'review' : 'reviews'}
      </span>
      <ul className={styles.bars} aria-label="Rating breakdown">
        {[5, 4, 3, 2, 1].map(star => {
          const count = summary.rating_distribution[String(star)] ?? 0;
          return (
            <li key={star} className={styles.bar}>
              <span>{star}</span>
              <span className={styles.barTrack}>
                <span className={styles.barFill} style={{ width: total ? `${(count / total) * 100}%` : 0 }} />
              </span>
              <span>{count}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function ProductReviews({
  productId,
  productName,
  reviews,
  summary,
  currentUserId,
}: {
  productId: string;
  productName: string;
  reviews: Review[];
  summary: RatingSummary | null;
  currentUserId: string | null;
}) {
  const total = summary?.total_reviews ?? 0;
  const { openSignIn } = useSignInModal();
  const ownReview = currentUserId ? reviews.find(review => review.user_id === currentUserId) : undefined;

  return (
    <section className={styles.section} aria-labelledby="product-reviews-heading">
      <div className={`${homeStyles.container} ${styles.layout}`}>
        <div>
          <h2 id="product-reviews-heading" className={styles.heading}>
            Reviews ({total})
          </h2>

          {summary && total > 0 && <Summary summary={summary} />}

          {reviews.length === 0 ? (
            <p className={styles.empty}>No reviews yet. Be the first to share your thoughts.</p>
          ) : (
            <ul className={styles.list}>
              {reviews.map(review => (
                <li key={review.id} className={styles.review}>
                  <div className={styles.reviewHead}>
                    <Stars value={review.rating} />
                    {/* The API exposes no reviewer name, only whether the purchase is verified. */}
                    <span className={styles.reviewer}>
                      {review.user_id === currentUserId ? 'Your review' : review.is_verified_purchase ? 'Verified buyer' : 'Customer'}
                    </span>
                    <time className={styles.date} dateTime={review.created_at}>
                      {formatDate(review.created_at)}
                    </time>
                  </div>
                  {review.title && <p className={styles.reviewTitle}>{review.title}</p>}
                  {review.comment && <p className={styles.reviewText}>{review.comment}</p>}
                  {review.images.length > 0 && (
                    <ul className={styles.photos} aria-label="Customer photos">
                      {review.images.map(image => (
                        <li key={image.id}>
                          <a
                            href={mediaUrl(image.image_url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={styles.photoLink}
                            aria-label="Open customer photo">
                            <Image src={mediaUrl(image.image_url)} alt={image.alt_text ?? 'Customer photo'} fill sizes="84px" />
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                  {currentUserId && review.user_id === currentUserId && (
                    <DeleteReviewButton reviewId={review.id} productId={productId} />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={styles.formCard}>
          <h3 className={styles.label}>Write a review</h3>
          {!currentUserId ? (
            <p className={styles.signIn}>
              <button type="button" className={styles.linkButton} onClick={() => openSignIn()}>
                Sign in
              </button>{' '}
              to review a product you have received.
            </p>
          ) : ownReview ? (
            <p className={styles.signIn}>You have reviewed this product. Thank you.</p>
          ) : (
            <WriteReviewForm productId={productId} productName={productName} />
          )}
        </div>
      </div>
    </section>
  );
}
