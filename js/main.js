/* ================================================
   STAFFPRO INC. — MAIN JAVASCRIPT
   ================================================ */

(function () {
  'use strict';

  /* --- Navigation: scroll shadow --- */
  const nav = document.getElementById('nav');
  if (nav) {
    window.addEventListener('scroll', () => {
      nav.classList.toggle('scrolled', window.scrollY > 20);
    }, { passive: true });
  }

  /* --- Mobile menu toggle --- */
  const toggle   = document.getElementById('navToggle');
  const mobileNav = document.getElementById('navMobile');

  if (toggle && mobileNav) {
    toggle.addEventListener('click', () => {
      const isOpen = toggle.classList.toggle('open');
      mobileNav.classList.toggle('open', isOpen);
      document.body.style.overflow = isOpen ? 'hidden' : '';
    });

    // Close on link click
    mobileNav.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        toggle.classList.remove('open');
        mobileNav.classList.remove('open');
        document.body.style.overflow = '';
      });
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!nav.contains(e.target) && !mobileNav.contains(e.target)) {
        toggle.classList.remove('open');
        mobileNav.classList.remove('open');
        document.body.style.overflow = '';
      }
    });
  }

  /* --- Set active nav link --- */
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-link, .nav-mobile-link').forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPath || (currentPath === '' && href === 'index.html')) {
      link.classList.add('active');
    }
  });

  /* --- Fade-in on scroll (Intersection Observer) --- */
  const fadeEls = document.querySelectorAll('.fade-in');
  if (fadeEls.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    fadeEls.forEach(el => observer.observe(el));
  } else {
    // Fallback: show all immediately
    fadeEls.forEach(el => el.classList.add('visible'));
  }

  /* --- Animated stat counters --- */
  function animateCount(el) {
    const target = parseInt(el.dataset.target, 10);
    const suffix = el.dataset.suffix || '';
    const duration = 1800;
    const start = performance.now();

    function step(now) {
      const elapsed  = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.floor(eased * target) + suffix;
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  const statEls = document.querySelectorAll('[data-target]');
  if (statEls.length && 'IntersectionObserver' in window) {
    const statObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCount(entry.target);
          statObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });
    statEls.forEach(el => statObserver.observe(el));
  }

  /* --- News card expand/collapse --- */
  document.querySelectorAll('.news-expand-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var card    = btn.closest('.news-card');
      var detail  = card.querySelector('.news-detail');
      var label   = btn.querySelector('.expand-label');
      var expanded = card.classList.toggle('expanded');
      btn.setAttribute('aria-expanded', expanded);
      detail.hidden  = !expanded;
      label.textContent = expanded ? 'Show less' : 'Read more';
    });
  });

  /* --- FAQ accordion --- */
  document.querySelectorAll('.faq-question').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item    = btn.closest('.faq-item');
      var answer  = item.querySelector('.faq-answer');
      var open    = item.classList.toggle('open');
      btn.setAttribute('aria-expanded', open);
      answer.hidden = !open;
    });
  });

  /* --- Contact form handler (Formspree) --- */
  const contactForm = document.getElementById('contactForm');
  if (contactForm) {
    contactForm.addEventListener('submit', function (e) {
      e.preventDefault();

      const btn = contactForm.querySelector('.form-submit');
      const originalLabel = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Sending…';

      const data = new FormData(contactForm);

      fetch('https://formspree.io/f/mnjroder', {
        method: 'POST',
        body: data,
        headers: { 'Accept': 'application/json' }
      })
      .then(function (response) {
        if (response.ok) {
          contactForm.style.display = 'none';
          const success = document.getElementById('formSuccess');
          if (success) success.classList.add('show');
        } else {
          btn.disabled = false;
          btn.textContent = originalLabel;
          alert('Something went wrong. Please try again or call us at (718) 471-1122.');
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.textContent = originalLabel;
        alert('Something went wrong. Please try again or call us at (718) 471-1122.');
      });
    });
  }

})();
