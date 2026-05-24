function VisualizationSubpanel({ title, variant = "chart", children }) {
  return (
    <section className={`visualization-subpanel subpanel-${variant}`}>
      <h3>{title}</h3>

      <div className="visualization-subpanel-content">{children}</div>
    </section>
  );
}

export default VisualizationSubpanel;
