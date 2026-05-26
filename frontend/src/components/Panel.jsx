import PopoutCard from "./PopoutCard";

function Panel({ title, children, popout = true, popoutName }) {
  return (
    <PopoutCard
      className="panel"
      title={title}
      titleLevel={2}
      popout={popout}
      popoutName={popoutName}>
      {children}
    </PopoutCard>
  );
}

export default Panel;
