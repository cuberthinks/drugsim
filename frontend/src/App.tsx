import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { PredictPage } from "./pages/PredictPage";
import { MethodologyPage } from "./pages/MethodologyPage";
import { LimitationsPage } from "./pages/LimitationsPage";
import { AboutPage } from "./pages/AboutPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { TermsPage } from "./pages/TermsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { ComparePage } from "./pages/ComparePage";
import { ChangelogPage } from "./pages/ChangelogPage";
import { SourcesPage } from "./pages/SourcesPage";
import { BenchmarkPage } from "./pages/BenchmarkPage";

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
          <Route path="history" element={<HistoryPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="changelog" element={<ChangelogPage />} />
          <Route path="sources" element={<SourcesPage />} />
          <Route path="benchmarks" element={<BenchmarkPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
