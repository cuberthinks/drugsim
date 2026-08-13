import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { PredictPage } from "./pages/PredictPage";
import { MethodologyPage } from "./pages/MethodologyPage";
import { LimitationsPage } from "./pages/LimitationsPage";
import { AboutPage } from "./pages/AboutPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { TermsPage } from "./pages/TermsPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="predict" element={<PredictPage />} />
          <Route path="methodology" element={<MethodologyPage />} />
          <Route path="limitations" element={<LimitationsPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="privacy" element={<PrivacyPage />} />
          <Route path="terms" element={<TermsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
