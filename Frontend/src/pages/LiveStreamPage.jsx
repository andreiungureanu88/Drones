import React, { useState } from "react";

import './../index.css' 
import Header from './../components/Header.jsx' 
import Hero from './../components/Hero.jsx' 
import Home from './../components/Home.jsx';
import FollowMe from './../components/FollowMe.jsx';
import SkyScan from './../components/SkyScan.jsx';
import LineTracker from './../components/LineTracker.jsx';
import Contact from './../components/Contact.jsx'; 

const LiveStreamPage = () => {
  const [currentPage, setCurrentPage] = useState('home');

  const handlePageChange = (page) => {
    setCurrentPage(page.toLowerCase());
  };

  const renderPage = () => {
    switch (currentPage) {
      case 'home':
        return <Home />;
      case 'followme':
        return <FollowMe />;
      case 'skyscan':
        return <SkyScan />;
      case 'linetracker':
        return <LineTracker />;
      case 'contact':
        return <Contact />;
      default:
        return <Home />;
    }
  };

  return (
    <>
      <Header onPageChange={handlePageChange} currentPage={currentPage} />
      <main>
        {renderPage()}
      </main>
    </>
  );
};

export default LiveStreamPage;
