import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { buildPopoutId } from "../utils/popoutIds";

function PopoutCard({
  title,
  titleLevel = 2,
  className,
  contentClassName,
  children,
  popout = true,
  popoutName,
  popoutSize = "width=520,height=720",
}) {
  const reactId = useId();
  const [isPoppedOut, setIsPoppedOut] = useState(false);
  const popupRef = useRef(null);
  const popoutId = useMemo(
    () => buildPopoutId(popoutName || title || reactId),
    [popoutName, reactId, title],
  );
  const headingId = `${popoutId}-title`;
  const TitleTag = `h${titleLevel}`;

  const closePopup = useCallback(() => {
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.close();
    }

    popupRef.current = null;
  }, []);

  const restoreCard = useCallback(() => {
    closePopup();
    setIsPoppedOut(false);
  }, [closePopup]);

  const openPopup = useCallback(() => {
    if (!popout) {
      return;
    }

    const popup = window.open(
      getPopoutUrl(popoutId),
      popoutId,
      `${popoutSize},resizable=yes,scrollbars=yes`,
    );

    if (!popup) {
      return;
    }

    popupRef.current = popup;
    popup.focus();
    setIsPoppedOut(true);
  }, [popout, popoutId, popoutSize]);

  useEffect(() => {
    if (!isPoppedOut) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      if (!popupRef.current || popupRef.current.closed) {
        popupRef.current = null;
        setIsPoppedOut(false);
      }
    }, 500);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [isPoppedOut]);

  useEffect(() => closePopup, [closePopup]);

  if (isPoppedOut) {
    return (
      <>
        <section className={`${className} popped-out-placeholder`} aria-labelledby={headingId}>
          <div className="popped-out-title-row">
            <TitleTag id={headingId}>{title}</TitleTag>
            <button className="popout-button" type="button" onClick={restoreCard}>
              Restore
            </button>
          </div>
        </section>

      </>
    );
  }

  return (
    <section className={className} aria-labelledby={headingId}>
      <CardHeader
        title={title}
        titleLevel={titleLevel}
        titleId={headingId}
        actionLabel="Pop out"
        onAction={openPopup}
        showAction={popout}
      />
      {contentClassName ? <div className={contentClassName}>{children}</div> : children}
    </section>
  );
}

function CardHeader({
  title,
  titleLevel,
  titleId,
  actionLabel,
  onAction,
  showAction = true,
}) {
  const TitleTag = `h${titleLevel}`;

  return (
    <div className="card-title-row">
      <TitleTag id={titleId}>{title}</TitleTag>
      {showAction && (
        <button className="popout-button" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}

function getPopoutUrl(popoutId) {
  const url = new URL(window.location.href);

  url.search = "";
  url.hash = "";
  url.searchParams.set("popout", popoutId);

  return url.toString();
}

export default PopoutCard;
