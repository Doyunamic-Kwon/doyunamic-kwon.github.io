document.addEventListener('DOMContentLoaded', () => {
  for (const placeholder of document.querySelectorAll('[data-empty-for]')) {
    const listing = document.getElementById(`listing-${placeholder.dataset.emptyFor}`)
      || document.getElementById(placeholder.dataset.emptyFor);
    const hasReviews = (listing?.querySelectorAll('.quarto-post').length ?? 0) > 0;
    placeholder.hidden = hasReviews;
    document.body.classList.toggle('has-reviews', hasReviews);
    if (!hasReviews && listing) listing.hidden = true;
  }

  const updateCategories = () => {
    const normalizePath = path => path.replace(/\/index\.html$/, '/');
    for (const link of document.querySelectorAll('#quarto-sidebar a.sidebar-item-text[href]')) {
      const target = new URL(link.href, location.href);
      const active = normalizePath(target.pathname) === normalizePath(location.pathname) && target.hash === location.hash;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  };
  updateCategories();
  window.addEventListener('hashchange', updateCategories);

  for (const link of document.querySelectorAll('#quarto-sidebar a.sidebar-link')) {
    link.addEventListener('click', () => {
      const toggle = document.querySelector('.quarto-secondary-nav button[aria-controls="quarto-sidebar"]');
      if (toggle?.getAttribute('aria-expanded') === 'true') toggle.click();
    });
  }

  for (const category of document.querySelectorAll('.listing-category')) {
    category.setAttribute('role', 'button');
    category.tabIndex = 0;
    category.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        category.click();
      }
    });
  }

  for (const table of document.querySelectorAll('main table')) {
    if (table.parentElement?.classList.contains('table-responsive')) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-responsive';
    table.before(wrapper);
    wrapper.append(table);
  }
});
