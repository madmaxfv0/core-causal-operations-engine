import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { Shell } from "./components/Shell";
import { ToastProvider } from "./components/ui";
import { I18nProvider } from "./lib/i18n";
import { primeDataSource } from "./lib/api";
import { Overview, QualityPage, Wells } from "./pages/Overview";
import { WellDetail } from "./pages/WellDetail";
import { CompareTreatments, InterventionDetail, Interventions } from "./pages/Interventions";
import { GhostBarrels, IdleWells, WaterEconomics } from "./pages/Field";
import { Portfolio, Scenarios } from "./pages/Portfolio";
import { Blind, ModelLab, ModelRuns, Network } from "./pages/Lab";
import { Archive, DataHub, DecisionLog, Imports, Settings, WhyCore } from "./pages/Ops";
import { Presentation } from "./pages/Presentation";
import { AlbertaMap } from "./pages/Map";
import { Guide } from "./pages/Guide";

primeDataSource();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <ToastProvider>
        <BrowserRouter>
          <Shell>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/wells" element={<Wells />} />
              <Route path="/wells/:id" element={<WellDetail />} />
              <Route path="/ghost" element={<GhostBarrels />} />
              <Route path="/idle" element={<IdleWells />} />
              <Route path="/network" element={<Network />} />
              <Route path="/map" element={<AlbertaMap />} />
              <Route path="/interventions" element={<Interventions />} />
              <Route path="/interventions/compare" element={<CompareTreatments />} />
              <Route path="/interventions/:id" element={<InterventionDetail />} />
              <Route path="/water" element={<WaterEconomics />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/portfolio/scenarios" element={<Scenarios />} />
              <Route path="/archive" element={<Archive />} />
              <Route path="/archive/ask" element={<Archive ask />} />
              <Route path="/model-lab" element={<ModelLab />} />
              <Route path="/model-lab/blind" element={<ModelLab initial="blind" />} />
              <Route path="/quality" element={<QualityPage />} />
              <Route path="/data" element={<DataHub />} />
              <Route path="/data/imports" element={<Imports />} />
              <Route path="/decisions" element={<DecisionLog />} />
              <Route path="/runs" element={<ModelRuns />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/guide" element={<Guide />} />
              <Route path="/why" element={<WhyCore />} />
              <Route path="/present" element={<Presentation />} />
              <Route path="*" element={<Overview />} />
            </Routes>
          </Shell>
        </BrowserRouter>
      </ToastProvider>
    </I18nProvider>
  </React.StrictMode>
);
