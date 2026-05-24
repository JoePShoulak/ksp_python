function VisualizationSubpanel({ title, className = "", children }) {
  return (
    <section className={`visualization-subpanel ${className}`}>
      <h3>{title}</h3>

      <div className="visualization-subpanel-content">{children}</div>
    </section>
  );
}

export default VisualizationSubpanel;
