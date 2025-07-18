import React from 'react';
import './../style/Loading.css';

const Loading = ({ message = "Se încarcă..." }) => {
  return (
    <div className="loading-container">
      <div className="loading-content">
        <div className="drone-loader">
          <div className="drone-body">
          </div>
          <div className="propeller propeller-1"></div>
          <div className="propeller propeller-2"></div>
          <div className="propeller propeller-3"></div>
          <div className="propeller propeller-4"></div>
          <div className="drone-shadow"></div>
        </div>
        <p className="loading-message">{message}</p>
      </div>
    </div>
  );
};

export default Loading;