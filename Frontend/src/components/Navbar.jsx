import { useRef, useEffect } from 'react';
import PropTypes from "prop-types";
import '../index.css';

const Navbar = ({ navOpen, onPageChange, currentPage }) => {
  const lastActiveLink = useRef();
  const activeBox = useRef();

  const initActiveBox = () => {
    if (lastActiveLink.current) {
      activeBox.current.style.top = lastActiveLink.current.offsetTop + 'px';
      activeBox.current.style.left = lastActiveLink.current.offsetLeft + 'px';
      activeBox.current.style.width = lastActiveLink.current.offsetWidth + 'px';
      activeBox.current.style.height = lastActiveLink.current.offsetHeight + 'px';
    }
  }

  useEffect(() => {
    // Găsește link-ul activ și setează-l ca lastActiveLink
    const activeLink = document.querySelector(`.nav-link[data-page="${currentPage}"]`);
    if (activeLink) {
      lastActiveLink.current = activeLink;
      lastActiveLink.current.classList.add('active');
      initActiveBox();
    }
  }, [currentPage]);

  useEffect(initActiveBox, []);
  window.addEventListener('resize', initActiveBox);

  const activeCurrentLink = (event, page) => {
    event.preventDefault();
    lastActiveLink.current?.classList.remove('active');
    event.target.classList.add('active');
    lastActiveLink.current = event.target;
    
    activeBox.current.style.top = lastActiveLink.current.offsetTop + 'px';
    activeBox.current.style.left = lastActiveLink.current.offsetLeft + 'px';
    activeBox.current.style.width = lastActiveLink.current.offsetWidth + 'px';
    activeBox.current.style.height = lastActiveLink.current.offsetHeight + 'px';
    
    onPageChange(page);
  }

  const navItems = [
    { label: 'Home', page: 'home' },
    { label: 'FollowMe', page: 'followme' },
    { label: 'SkyScan', page: 'skyscan' },
    { label: 'LineTracker', page: 'linetracker' },
    { label: 'Contact', page: 'contact' }
  ];

  return (
    <nav className={`navbar ${navOpen ? 'active' : ''}`}>
      {navItems.map(({ label, page }, key) => (
        <a
          href="#"
          key={key}
          data-page={page}
          className={`nav-link ${currentPage === page ? 'active' : ''}`}
          ref={currentPage === page ? lastActiveLink : null}
          onClick={(e) => activeCurrentLink(e, page)}
        >
          {label}
        </a>
      ))}
      <div
        className="active-box"
        ref={activeBox}
      ></div>
    </nav>
  );
};

Navbar.propTypes = {
  navOpen: PropTypes.bool.isRequired,
  onPageChange: PropTypes.func.isRequired,
  currentPage: PropTypes.string.isRequired
};

export default Navbar;