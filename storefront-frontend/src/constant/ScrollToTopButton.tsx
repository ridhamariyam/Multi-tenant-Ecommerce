'use client';
import { useEffect, useState, type CSSProperties } from 'react';

/** Floating "back to top" control, shown after the viewer scrolls down. */
const ScrollToTopButton = () => {
  const [isVisible, setIsVisible] = useState<boolean>(false);

  useEffect(() => {
    const handleScroll = () => setIsVisible(window.scrollY > 1000);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToTop = (): void => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const style: CSSProperties = {
    position: 'fixed',
    right: 'clamp(16px, 2.8vw, 40px)',
    bottom: 'clamp(16px, 2.8vw, 40px)',
    zIndex: 60,
    width: 46,
    height: 46,
    display: 'grid',
    placeItems: 'center',
    border: 'none',
    borderRadius: '50%',
    background: '#1a1714',
    color: '#fbfaf8',
    cursor: 'pointer',
    boxShadow: '0 6px 20px rgba(0,0,0,0.18)',
    opacity: isVisible ? 1 : 0,
    transform: isVisible ? 'translateY(0)' : 'translateY(10px)',
    transition: 'opacity 0.3s ease, transform 0.3s ease',
    pointerEvents: isVisible ? 'auto' : 'none',
  };

  return (
    <button className="scroll-to-top" type="button" style={style} onClick={scrollToTop} aria-label="Back to top">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M12 19V5M5 12l7-7 7 7" />
      </svg>
    </button>
  );
};

export default ScrollToTopButton;
