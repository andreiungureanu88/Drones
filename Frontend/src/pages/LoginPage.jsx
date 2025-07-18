import { useNavigate } from "react-router-dom";
import '../style/LoginPage.css'; 

const LoginPage = () => {
  const navigate = useNavigate(); 

  const handleButtonClick = () => {
    navigate("/livestream"); 
  };

  return (
    <div className="flex-1 overflow-auto relative z-10 login-page-container">
      <div className="banner-video-container">
        <div className="video-player-component">
          <div className="video-player-box">
            <div className="video-player-wrapper">
              <div className="video-player-poster"></div>
              <video loop autoPlay muted playsInline className="video-player-dom">
                <source type="video/mp4" src="https://dji-official-fe.djicdn.com/reactor/assets/_next/static/videos/e6fb5809-2024-4fcf-ac34-bb30becffd6a.mp4" />
              </video>
            </div>
          </div>
        </div>
      </div>

      <div className="centered-content">
        <h1 className="centered-title">SKY DRONE HUB</h1>
        <button className="get-started-btn" onClick={handleButtonClick}>
          Get Started
        </button>
      </div>
    </div>
  );
}

export default LoginPage;
