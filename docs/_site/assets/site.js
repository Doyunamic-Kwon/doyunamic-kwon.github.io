document.addEventListener('DOMContentLoaded', () => {
  const placeholders = [...document.querySelectorAll('[data-empty-for]')];
  for (const placeholder of placeholders) {
    const listing = document.getElementById(`listing-${placeholder.dataset.emptyFor}`)
      || document.getElementById(placeholder.dataset.emptyFor);
    const entries = listing?.querySelectorAll('.quarto-post, .quarto-grid-item, tbody tr') ?? [];
    const hasReviews = entries.length > 0;
    placeholder.hidden = hasReviews;
    document.body.classList.toggle('has-reviews', hasReviews);
    document.body.classList.toggle('has-no-reviews', !hasReviews);
    if (!hasReviews && listing) listing.style.display = 'none';
  }
  for (const table of document.querySelectorAll('main table')) {
    if (table.parentElement?.classList.contains('table-responsive')) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-responsive';
    table.before(wrapper);
    wrapper.append(table);
  }
});

