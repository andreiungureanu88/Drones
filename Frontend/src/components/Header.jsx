import Navbar from "./Navbar";
import '../index.css';
import { useState } from 'react';

const Header = ({ onPageChange, currentPage }) => {
  const [navOpen, setNavOpen] = useState(false);

  const handleLogoClick = (e) => {
    e.preventDefault();
    onPageChange('home');
  };

  return (
    <header className="fixed top-0 left-0 w-full h-20 flex items-center z-40 bg-gradient-to-b from-zinc-900 to-zinc-900/0">
      <div className="max-w-screen-2xl w-full mx-auto px-4 flex justify-between items-center md:px-6">
        <div className="flex items-center">
          {/* Logo-ul schimbă pagina la Home */}
          <a href="#" className="logo" onClick={handleLogoClick}>
            <img src="/logo.svg" width={40} height={40} alt="logo" />
          </a>
        </div>

        <div className="flex items-center justify-center flex-grow">
          <Navbar 
            navOpen={navOpen} 
            onPageChange={onPageChange} 
            currentPage={currentPage} 
          />
        </div>

        <div className="flex items-center">
          <button 
            className="menu-btn md:hidden" 
            onClick={() => setNavOpen((prev) => !prev)}
          >
            <span className="material-symbols-rounded">
              {navOpen ? 'close' : 'menu'}
            </span>
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;