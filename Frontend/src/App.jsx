import LoginPage from "./pages/LoginPage";
import LiveStreamPage from "./pages/LiveStreamPage";
import { Route, Routes, useLocation } from "react-router-dom";
import './index.css'
function App() {
  const location = useLocation();

  return (
    <div className="body">
     

      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/livestream" element={<LiveStreamPage />} />
      </Routes>
    </div>
  );
}

export default App;
