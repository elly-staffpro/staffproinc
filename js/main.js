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
    /* Shipping: flat rate for the first poster, reduced rate for each one after. */
    const SHIP_FIRST = 18.95;
    const SHIP_ADDITIONAL = 9.75;

    const linesEl = document.getElementById('orderLines');
    const emptyEl = document.getElementById('orderEmpty');
    const statesEl = document.getElementById('otherStates');
    const stateTpl = document.getElementById('otherStateTemplate');

    function money(n) { return '$' + n.toFixed(2); }
    function allQtyInputs() {
      return Array.prototype.slice.call(posterForm.querySelectorAll('.qty-input'));
    }

    /* --- repeatable "all other states" rows --- */
    function refreshRemoveButtons() {
      const rows = statesEl.querySelectorAll('.other-row');
      rows.forEach(function (r) {
        r.querySelector('.os-remove').hidden = (rows.length <= 1);
      });
    }

    function addStateRow() {
      statesEl.appendChild(stateTpl.content.cloneNode(true));
      refreshRemoveButtons();
      render();
    }

    statesEl.addEventListener('click', function (e) {
      const btn = e.target.closest('.os-remove');
      if (!btn) return;
      const rows = statesEl.querySelectorAll('.other-row');
      if (rows.length <= 1) return;
      btn.closest('.other-row').remove();
      refreshRemoveButtons();
      render();
    });

    const addBtn = document.getElementById('addStateRow');
    if (addBtn) addBtn.addEventListener('click', addStateRow);

    /* Describe a row for the totals list and the order email. */
    function describe(input) {
      const row = input.closest('.product-row');
      if (input.dataset.label) {                       // fixed NY / NJ rows
        // Each language has its own quantity box, so the language lives on the input
        return { name: input.dataset.label, option: input.dataset.lang || '', missing: null };
      }
      const stateSel = row.querySelector('.os-state');  // repeatable rows
      const langSel = row.querySelector('.os-lang');
      const stateName = stateSel.options[stateSel.selectedIndex]
        ? stateSel.options[stateSel.selectedIndex].text : '';
      return {
        name: stateSel.value ? stateName + ' Poster' : '',
        option: langSel ? langSel.value : '',
        missing: stateSel.value ? null : stateSel
      };
    }

    function shippingFor(totalQty) {
      if (totalQty < 1) return 0;
      return SHIP_FIRST + (totalQty - 1) * SHIP_ADDITIONAL;
    }

    function currentLines() {
      const out = [];
      allQtyInputs().forEach(function (input) {
        const qty = parseInt(input.value, 10);
        if (!qty || qty < 1) return;
        const price = parseFloat(input.dataset.price);
        const d = describe(input);
        out.push({
          label: d.name, option: d.option, missing: d.missing,
          qty: qty, price: price, subtotal: qty * price
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
      let totalQty = 0;
      let html = '';
      lines.forEach(function (l) {
        items += l.subtotal;
        totalQty += l.qty;
        const base = l.label || 'Select a state';
        const name = l.option ? (base + ' (' + l.option + ')') : base;
        html += '<div class="order-line"><span>' + name + ' &times; ' + l.qty + '</span><span>' + money(l.subtotal) + '</span></div>';
      });

      const ship = shippingFor(totalQty);
      const shipDetail = totalQty > 1
        ? ' (' + money(SHIP_FIRST) + ' first, ' + money(SHIP_ADDITIONAL) + ' &times; ' + (totalQty - 1) + ')'
        : '';
      html += '<div class="order-line"><span>Shipping' + shipDetail + '</span><span>' + money(ship) + '</span></div>';
      html += '<div class="order-line total"><span>Estimated Total</span><span>' + money(items + ship) + '</span></div>';
      html += '<p class="order-note">' + money(SHIP_FIRST) + ' shipping for the first poster, ' + money(SHIP_ADDITIONAL) + ' for each additional. We’ll confirm the final amount before billing.</p>';
      linesEl.innerHTML = html;
    }

    // Keep each repeatable row's heading in step with its state selection
    function syncRowNames() {
      statesEl.querySelectorAll('.other-row').forEach(function (row) {
        const sel = row.querySelector('.os-state');
        const nameEl = row.querySelector('.os-name');
        const txt = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : '';
        nameEl.textContent = sel.value ? txt + ' Poster' : 'Select a state';
        nameEl.style.color = sel.value ? 'var(--color-text)' : '';
      });
    }

    posterForm.addEventListener('input', function () { syncRowNames(); render(); });
    posterForm.addEventListener('change', function () { syncRowNames(); render(); });

    addStateRow();   // start with one row present

    posterForm.addEventListener('submit', function (e) {
      e.preventDefault();

      const lines = currentLines();
      if (!lines.length) {
        alert('Please enter a quantity for at least one poster before submitting.');
        return;
      }
      // A state must be chosen on any repeatable row that has a quantity
      const missing = lines.filter(function (l) { return l.missing; })[0];
      if (missing) {
        alert('Please choose a state for each poster you ordered.');
        missing.missing.focus();
        return;
      }

      // Compose a readable order block so the notification email is workable as-is
      let items = 0;
      let totalQty = 0;
      let summary = 'POSTER ORDER\n------------------------------\n';
      lines.forEach(function (l) {
        items += l.subtotal;
        totalQty += l.qty;
        const name = l.option ? (l.label + ' (' + l.option + ')') : l.label;
        summary += l.qty + ' x ' + name + ' @ ' + money(l.price) + ' = ' + money(l.subtotal) + '\n';
      });
      const ship = shippingFor(totalQty);
      summary += '------------------------------\n';
      summary += 'Posters: ' + totalQty + '\n';
      summary += 'Shipping: ' + money(ship);
      if (totalQty > 1) {
        summary += '  (' + money(SHIP_FIRST) + ' first + ' + money(SHIP_ADDITIONAL) + ' x ' + (totalQty - 1) + ')';
      }
      summary += '\nESTIMATED TOTAL: ' + money(items + ship) + '\n';
      document.getElementById('orderSummary').value = summary;

      // Name the repeatable rows so they arrive as readable fields too.
      // Rows left empty stay unnamed, so they aren't submitted at all.
      let n = 0;
      statesEl.querySelectorAll('.other-row').forEach(function (row) {
        const stateSel = row.querySelector('.os-state');
        const langSel = row.querySelector('.os-lang');
        const qtyEl = row.querySelector('.os-qty');
        const qty = parseInt(qtyEl.value, 10);
        if (!qty || qty < 1) {
          stateSel.removeAttribute('name');
          langSel.removeAttribute('name');
          qtyEl.removeAttribute('name');
          return;
        }
        n += 1;
        stateSel.name = 'Other State ' + n;
        langSel.name = 'Other State ' + n + ' Language';
        qtyEl.name = 'Other State ' + n + ' Qty';
      });

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
