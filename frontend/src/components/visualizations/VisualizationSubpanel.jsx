function VisualizationSubpanel({ title, children }) {
  return (
    <section className="visualization-subpanel">
      <h3>{title}</h3>

      <div className="visualization-subpanel-content">{children}</div>
    </section>
  );
}

export default VisualizationSubpanel;
