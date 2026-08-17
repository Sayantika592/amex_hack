import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Shell } from "./components/ui.jsx";
import { Dashboard, Disputes } from "./pages/Dashboard.jsx";
import DisputeDetail from "./pages/DisputeDetail.jsx";
import { NewDispute, Demo, Taxonomy, Models } from "./pages/Other.jsx";

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/disputes" element={<Disputes />} />
        <Route path="/disputes/:id" element={<DisputeDetail />} />
        <Route path="/new" element={<NewDispute />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/taxonomy" element={<Taxonomy />} />
        <Route path="/models" element={<Models />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
