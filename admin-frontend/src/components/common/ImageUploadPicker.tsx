import { useEffect, useId, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import "./imageUploadPicker.css";

/** A compact image-only file picker. Camera capture is offered when the browser supports it. */
function ImageUploadPicker({
  onFiles,
  inputLabel,
  buttonLabel = "Upload images",
  accept,
  multiple = false,
  disabled = false,
  id,
  "aria-describedby": describedBy,
  "aria-invalid": invalid,
  "aria-required": required,
}: {
  onFiles: (files: File[]) => void;
  inputLabel: string;
  buttonLabel?: string;
  accept: string;
  multiple?: boolean;
  disabled?: boolean;
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
  "aria-required"?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);
  const deviceInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const cameraRequest = useRef(0);

  const closeCamera = () => {
    cameraRequest.current += 1;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
    setCameraOpen(false);
    setCameraReady(false);
    setCameraError(null);
  };
  useEffect(() => () => {
    cameraRequest.current += 1;
    stream.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const closeEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
    };
  }, [open]);

  const chooseDevice = () => {
    setOpen(false);
    deviceInput.current?.click();
  };
  const chooseCamera = async () => {
    setOpen(false);
    if (!navigator.mediaDevices?.getUserMedia) return cameraInput.current?.click();
    const request = ++cameraRequest.current;
    setCameraOpen(true);
    setCameraReady(false);
    setCameraError(null);
    try {
      const captured = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: "environment" } } });
      if (request !== cameraRequest.current) return captured.getTracks().forEach((track) => track.stop());
      stream.current = captured;
      setCameraReady(true);
      if (video.current) {
        video.current.srcObject = captured;
        void video.current.play().catch(() => setCameraError("Camera preview could not start. Try the device picker instead."));
      }
    } catch {
      if (request === cameraRequest.current) setCameraError("Camera access is unavailable. Allow camera permission or choose an image from your device.");
    }
  };
  const takePhoto = () => {
    const source = video.current;
    if (!source?.videoWidth || !source.videoHeight) return setCameraError("The camera is still starting. Try again in a moment.");
    const canvas = document.createElement("canvas");
    canvas.width = source.videoWidth;
    canvas.height = source.videoHeight;
    canvas.getContext("2d")?.drawImage(source, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return setCameraError("Could not capture the photo. Try again.");
      onFiles([new File([blob], `photo-${Date.now()}.jpg`, { type: "image/jpeg" })]);
      closeCamera();
    }, "image/jpeg", .9);
  };
  const selected = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    if (files.length) onFiles(files);
  };

  return <div className="image-upload-picker" ref={root}>
    <button type="button" id={id} className="image-upload-trigger" disabled={disabled} aria-expanded={open} aria-controls={menuId} aria-describedby={describedBy} aria-invalid={invalid} aria-required={required} onClick={() => setOpen((current) => !current)}>
      <span aria-hidden="true">＋</span> {buttonLabel}
    </button>
    {open && <div id={menuId} className="image-upload-menu" role="menu" aria-label="Image source">
      <button type="button" role="menuitem" onClick={() => void chooseCamera()}>Take photo <small>Open camera</small></button>
      <button type="button" role="menuitem" onClick={chooseDevice}>Upload from device <small>Browse files</small></button>
    </div>}
    <input ref={deviceInput} type="file" accept={accept} multiple={multiple} aria-label={inputLabel} onChange={selected} hidden />
    <input ref={cameraInput} type="file" accept={accept} capture="environment" aria-label={`${inputLabel} camera`} onChange={selected} hidden />
    {cameraOpen && <div className="image-camera-backdrop" role="presentation">
      <div className="image-camera-dialog" role="dialog" aria-modal="true" aria-label="Take photo">
        <div className="image-camera-header"><strong>Take photo</strong><button type="button" onClick={closeCamera} aria-label="Close camera">×</button></div>
        <video ref={video} autoPlay playsInline muted aria-label="Camera preview" />
        {cameraError && <p className="status status-error" role="alert">{cameraError}</p>}
        <div className="image-camera-actions"><button type="button" onClick={closeCamera}>Cancel</button><button type="button" className="primary" disabled={!cameraReady} onClick={takePhoto}>Capture photo</button><button type="button" onClick={() => { closeCamera(); cameraInput.current?.click(); }}>Use device picker</button></div>
      </div>
    </div>}
  </div>;
}

export default ImageUploadPicker;
