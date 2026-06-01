/* LMS Pagination shared script — v3
   - One-screen-at-a-time display
   - 3 sub-steps per page split by '---'
   - Top/bottom nav with Prev/Next
   - Keyboard navigation (left/right)
   - Deep-linking via ?step=1..3
   - Accessible focus management and ARIA updates
*/

(function () {
  'use strict';

  // Utility: parse query parameters
  function getQueryParams() {
    const params = new URLSearchParams(window.location.search);
    return {
      step: parseInt(params.get('step') || '1', 10)
    };
  }

  // Utility: update URL without adding to history
  function replaceQueryParam(key, value) {
    const url = new URL(window.location.href);
    if (value == null) {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, String(value));
    }
    window.history.replaceState({}, '', url);
  }

  // Find sections and core elements
  function init() {
    const sections = Array.from(document.querySelectorAll('.lms-section'));
    if (!sections.length) {
      // Nothing to paginate
      return;
    }

    // Controls (top)
    const prevTop = document.querySelector('[data-lms-action="prev-top"]');
    const nextTop = document.querySelector('[data-lms-action="next-top"]');
    const progressBarTop = document.querySelector('[data-lms-progress="bar-top"]');
    const progressTextTop = document.querySelector('[data-lms-progress="text-top"]');

    // Controls (bottom)
    const prevBottom = document.querySelector('[data-lms-action="prev-bottom"]');
    const nextBottom = document.querySelector('[data-lms-action="next-bottom"]');
    const progressBarBottom = document.querySelector('[data-lms-progress="bar-bottom"]');
    const progressTextBottom = document.querySelector('[data-lms-progress="text-bottom"]');

    const totalSteps = sections.length; // Expected 3 per page

    // Initial step from URL
    let currentStep = clampStep(getQueryParams().step, totalSteps);

    // Wire button handlers
    function onPrev() {
      if (currentStep > 1) {
        currentStep -= 1;
        render();
      }
    }
    function onNext() {
      if (currentStep < totalSteps) {
        currentStep += 1;
        render();
      }
    }

    prevTop && prevTop.addEventListener('click', onPrev);
    nextTop && nextTop.addEventListener('click', onNext);
    prevBottom && prevBottom.addEventListener('click', onPrev);
    nextBottom && nextBottom.addEventListener('click', onNext);

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
      // Ignore when focused on input/textarea/select or contenteditable
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      const isFormField = tag === 'input' || tag === 'textarea' || tag === 'select' || (e.target && e.target.isContentEditable);
      if (isFormField) return;

      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        onPrev();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        onNext();
      }
    });

    // Render current state
    function render() {
      // Sections visibility
      sections.forEach((sec, idx) => {
        const isActive = idx === (currentStep - 1);
        sec.classList.toggle('is-active', isActive);
        sec.setAttribute('aria-hidden', String(!isActive));
      });

      // Update buttons enable/disable
      const atStart = currentStep === 1;
      const atEnd = currentStep === totalSteps;
      [prevTop, prevBottom].forEach(btn => {
        if (!btn) return;
        btn.disabled = atStart;
        btn.setAttribute('aria-disabled', String(atStart));
      });
      [nextTop, nextBottom].forEach(btn => {
        if (!btn) return;
        btn.disabled = atEnd;
        btn.setAttribute('aria-disabled', String(atEnd));
      });

      // Progress values
      const pct = Math.round((currentStep / totalSteps) * 100);
      [progressBarTop, progressBarBottom].forEach(bar => {
        if (!bar) return;
        bar.style.width = pct + '%';
        bar.setAttribute('aria-valuenow', String(pct));
      });
      const label = `Step ${currentStep} of ${totalSteps}`;
      [progressTextTop, progressTextBottom].forEach(txt => {
        if (!txt) return;
        txt.textContent = label;
      });

      // Update URL
      replaceQueryParam('step', currentStep);

      // Focus management: removed to prevent unwanted outlines
      // const active = sections[currentStep - 1];
      // if (active) {
      //   const heading = active.querySelector('h1, h2, h3, h4, h5, h6');
      //   if (heading) {
      //     // Ensure focusable for programmatic focus
      //     const prevTabIndex = heading.getAttribute('tabindex');
      //     heading.setAttribute('tabindex', '-1');
      //     heading.focus({ preventScroll: false });
      //     // Keep tabindex so it remains focusable for A11y outline (as per CSS)
      //     if (prevTabIndex === null) {
      //       // leave -1 in place for subsequent navigations
      //     }
      //   } else {
      //     // Fallback: focus section itself
      //     active.setAttribute('tabindex', '-1');
      //     active.focus({ preventScroll: false });
      //   }
      // }
    }

    // Initial paint
    render();
  }

  function clampStep(n, total) {
    if (!Number.isFinite(n) || n < 1) return 1;
    if (n > total) return total;
    return n;
  }

  // Initialize after DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();