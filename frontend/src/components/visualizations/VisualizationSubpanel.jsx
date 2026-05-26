import PopoutCard from "../PopoutCard";

function VisualizationSubpanel({
  title,
  variant = "chart",
  popout = true,
  popoutName,
  children,
}) {
  return (
    <PopoutCard
      className={`visualization-subpanel subpanel-${variant}`}
      contentClassName="visualization-subpanel-content"
      title={title}
      titleLevel={3}
      popout={popout}
      popoutName={popoutName || title}>
      {children}
    </PopoutCard>
  );
}

export default VisualizationSubpanel;
