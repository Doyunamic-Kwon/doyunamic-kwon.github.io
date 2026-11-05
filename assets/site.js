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
  const categoryHost = document.getElementById('review-categories');
  const categoryList = document.querySelector('.quarto-listing-category');
  const categoryReset = document.querySelector('.quarto-listing-category-title');
  if (categoryHost && categoryList && categoryReset && document.body.classList.contains('has-reviews')) {
    categoryReset.textContent = '전체';
    categoryReset.classList.add('category-reset');
    categoryHost.append(categoryReset, categoryList);
    for (const control of [categoryReset, ...categoryList.querySelectorAll('.category')]) {
      control.setAttribute('role', 'button');
      control.tabIndex = 0;
      control.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          control.click();
        }
      });
    }
  }
  for (const input of document.querySelectorAll('.quarto-listing-filter input')) {
    input.setAttribute('aria-label', '리뷰 검색');
    input.placeholder = '리뷰 검색';
  }
});

