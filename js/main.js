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

  /* --- Labor law poster order form --- */
  const posterForm = document.getElementById('posterOrderForm');
  if (posterForm) {
    const SHIPPING = 18.50;
    const qtyInputs = Array.prototype.slice.call(posterForm.querySelectorAll('.qty-input'));
    const linesEl = document.getElementById('orderLines');
    const emptyEl = document.getElementById('orderEmpty');

    function money(n) { return '$' + n.toFixed(2); }

    // Which <select> qualifies a given product row (language or state)
    function optionFor(input) {
      const row = input.closest('.product-row');
      const sel = row ? row.querySelector('select') : null;
      if (!sel) return { label: '', value: '', el: null };
      return { label: sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : '', value: sel.value, el: sel };
    }

    function currentLines() {
      const out = [];
      qtyInputs.forEach(function (input) {
        const qty = parseInt(input.value, 10);
        if (!qty || qty < 1) return;
        const price = parseFloat(input.dataset.price);
        const opt = optionFor(input);
        out.push({
          label: input.dataset.label,
          option: opt.value ? opt.label : '',
          qty: qty,
          price: price,
          subtotal: qty * price
        });
      });
      return out;
    }

    function render() {
      const lines = currentLines();
      if (!lines.length) {
        emptyEl.hidden = false;
        linesEl.hidden = true;
        linesEl.innerHTML = '';
        return;
      }
      emptyEl.hidden = true;
      linesEl.hidden = false;

      let items = 0;
      let html = '';
      lines.forEach(function (l) {
        items += l.subtotal;
        const name = l.option ? (l.label + ' (' + l.option + ')') : l.label;
        html += '<div class="order-line"><span>' + name + ' &times; ' + l.qty + '</span><span>' + money(l.subtotal) + '</span></div>';
      });
      html += '<div class="order-line"><span>Shipping (estimated)</span><span>' + money(SHIPPING) + '</span></div>';
      html += '<div class="order-line total"><span>Estimated Total</span><span>' + money(items + SHIPPING) + '</span></div>';
      html += '<p class="order-note">Shipping is an estimate and may vary with quantity. We’ll confirm the final amount before billing.</p>';
      linesEl.innerHTML = html;
    }

    posterForm.addEventListener('input', render);
    posterForm.addEventListener('change', render);
    render();

    posterForm.addEventListener('submit', function (e) {
      e.preventDefault();

      const lines = currentLines();
      if (!lines.length) {
        alert('Please enter a quantity for at least one poster before submitting.');
        return;
      }
      // A state must be chosen for the "All Other States" rows when ordered
      let missingState = null;
      qtyInputs.forEach(function (input) {
        const qty = parseInt(input.value, 10);
        if (!qty || qty < 1) return;
        const opt = optionFor(input);
        if (opt.el && opt.el.value === '') missingState = opt.el;
      });
      if (missingState) {
        alert('Please choose a state for the poster you ordered.');
        missingState.focus();
        return;
      }

      // Compose a readable order block so the notification email is workable as-is
      let items = 0;
      let summary = 'POSTER ORDER\n------------------------------\n';
      lines.forEach(function (l) {
        items += l.subtotal;
        const name = l.option ? (l.label + ' (' + l.option + ')') : l.label;
        summary += l.qty + ' x ' + name + ' @ ' + money(l.price) + ' = ' + money(l.subtotal) + '\n';
      });
      summary += '------------------------------\n';
      summary += 'Shipping (estimated): ' + money(SHIPPING) + '\n';
      summary += 'ESTIMATED TOTAL: ' + money(items + SHIPPING) + '\n';
      summary += '\nShipping is an estimate and may vary with quantity.';
      document.getElementById('orderSummary').value = summary;

      const btn = posterForm.querySelector('.form-submit');
      const originalLabel = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Sending…';

      fetch('https://api.web3forms.com/submit', {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: new FormData(posterForm)
      })
      .then(function (response) { return response.json().then(function (d) { return { ok: response.ok, data: d }; }); })
      .then(function (res) {
        if (res.ok && res.data.success) {
          posterForm.style.display = 'none';
          const success = document.getElementById('posterSuccess');
          if (success) success.classList.add('show');
        } else {
          btn.disabled = false;
          btn.textContent = originalLabel;
          alert('Something went wrong sending your order. Please try again or call us at (718) 471-1122.');
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.textContent = originalLabel;
        alert('Something went wrong sending your order. Please try again or call us at (718) 471-1122.');
      });
    });
  }

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
