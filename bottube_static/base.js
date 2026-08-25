/* Header layout fix for mobile overlap */
if (window.innerWidth <= 480) {
  const header = document.querySelector('header');
  const logo = document.querySelector('.logo');
  const searchForm = document.querySelector('.search-form');
  if (header && logo && searchForm) {
    logo.style.minWidth = '120px';
    logo.style.flexShrink = '0';
    searchForm.style.flexGrow = '1';
    searchForm.style.marginLeft = '10px';
  }
}