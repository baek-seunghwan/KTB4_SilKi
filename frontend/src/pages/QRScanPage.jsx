import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import jsQR from "jsqr";
import MobileLayout from "../components/layout/MobileLayout";
import UserTopBar from "../components/layout/UserTopBar";
import qrHelpImage from "../assets/qr_img.png";
import { getStoreIdFromQr, getVoiceOrderPathFromQr } from "../api/orders";
import { getOrderContext } from "../api/stores";
import { hasPublicMenuData } from "../api/menus";

const QRScannerIcon = () => {
  return (
    <svg
      aria-hidden="true"
      className="size-12"
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M8 18V10C8 8.89543 8.89543 8 10 8H18M30 8H38C39.1046 8 40 8.89543 40 10V18M40 30V38C40 39.1046 39.1046 40 38 40H30M18 40H10C8.89543 40 8 39.1046 8 38V30"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M16 16H22V22H16V16ZM26 16H32V22H26V16ZM16 26H22V32H16V26ZM27 27H32V32H27V27Z"
        fill="currentColor"
      />
    </svg>
  );
};

const CameraSwitchIcon = () => {
  return (
    <svg
      aria-hidden="true"
      className="size-6"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.25l1.1-1.5h6.3L16.25 6h1.25A2.5 2.5 0 0 1 20 8.5v7a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 15.5v-7Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9 11a3.25 3.25 0 0 1 5.75-1.95M15 13a3.25 3.25 0 0 1-5.75 1.95"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="m14.7 7.8.15 1.55-1.55.15M9.3 16.2l-.15-1.55 1.55-.15"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

const QRScanPage = () => {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const animationFrameRef = useRef(null);
  const isDetectedRef = useRef(false);
  const [cameraFacingMode, setCameraFacingMode] = useState("environment");
  const [isHelpModalOpen, setIsHelpModalOpen] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [scanError, setScanError] = useState("");
  const [scanAttempt, setScanAttempt] = useState(0);

  const handleSwitchCamera = () => {
    isDetectedRef.current = false;
    setCameraFacingMode((currentFacingMode) =>
      currentFacingMode === "environment" ? "user" : "environment",
    );
  };

  const handleRetryScan = () => {
    isDetectedRef.current = false;
    setScanError("");
    setScanAttempt((currentAttempt) => currentAttempt + 1);
  };

  useEffect(() => {
    let isMounted = true;
    let detector = null;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { willReadFrequently: true });

    const stopCamera = () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    };

    const failScan = (message) => {
      if (!isMounted) {
        return false;
      }

      isDetectedRef.current = true;
      setScanError(message);
      stopCamera();
      return false;
    };

    const handleDetectedCode = async (value) => {
      const storeId = getStoreIdFromQr(value);
      const orderPath = getVoiceOrderPathFromQr(value);

      if (!storeId || !orderPath) {
        return failScan("가게 인식표를 인식하지 못했어요");
      }

      isDetectedRef.current = true;

      const rejectDetectedCode = (message) => {
        return failScan(message);
      };

      try {
        const orderContext = await getOrderContext(storeId);

        if (!isMounted) {
          return false;
        }

        if (!orderContext.orderAvailable) {
          return rejectDetectedCode(orderContext.message);
        }

        const hasMenus = await hasPublicMenuData(storeId);

        if (!isMounted) {
          return false;
        }

        if (!hasMenus) {
          return rejectDetectedCode("주문 가능한 메뉴가 등록되지 않은 가게예요");
        }

        setScanResult({
          orderPath,
          storeName: orderContext.storeName,
        });
        stopCamera();
        return true;
      } catch (error) {
        return rejectDetectedCode(
          error.status === 404
            ? "등록된 가게가 아니에요. 다시 맞춰주세요"
            : "가게 정보를 확인하지 못했어요. 잠시 후 다시 시도해주세요",
        );
      }
    };

    const detectWithBarcodeDetector = async (video) => {
      if (!detector) {
        return false;
      }

      const codes = await detector.detect(video);

      if (codes.length > 0) {
        return handleDetectedCode(codes[0].rawValue);
      }

      return false;
    };

    const detectWithCanvas = async (video) => {
      if (!context || !video.videoWidth || !video.videoHeight) {
        return false;
      }

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      const code = jsQR(imageData.data, imageData.width, imageData.height, {
        inversionAttempts: "dontInvert",
      });

      if (code?.data) {
        return await handleDetectedCode(code.data);
      }

      return false;
    };

    const scanQRCode = async () => {
      if (!isMounted || isDetectedRef.current) {
        return;
      }

      const video = videoRef.current;

      if (video && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        try {
          const isDetected = detector
            ? await detectWithBarcodeDetector(video)
            : await detectWithCanvas(video);

          if (isDetected) {
            return;
          }
        } catch {
          await detectWithCanvas(video);
        }
      }

      animationFrameRef.current = requestAnimationFrame(scanQRCode);
    };

    const startCamera = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        failScan("카메라를 사용할 수 없는 환경이에요");
        return;
      }

      try {
        if ("BarcodeDetector" in window) {
          detector = new window.BarcodeDetector({ formats: ["qr_code"] });
        }

        const fallbackFacingMode =
          cameraFacingMode === "environment" ? "user" : "environment";
        let stream;

        try {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
              facingMode: { exact: cameraFacingMode },
            },
          });
        } catch {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
              facingMode: fallbackFacingMode,
            },
          });
        }

        if (!isMounted) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        streamRef.current = stream;

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
          scanQRCode();
        }
      } catch {
        failScan("QR 스캔에 실패했어요");
      }
    };

    startCamera();

    return () => {
      isMounted = false;
      stopCamera();
    };
  }, [cameraFacingMode, scanAttempt]);

  return (
    <MobileLayout
      surfaceClassName="customer-page bg-surface-container-lowest"
      contentClassName="relative flex min-h-[inherit] w-full flex-col overflow-hidden bg-surface-container-lowest px-0 py-0"
    >
      <UserTopBar onActionClick={() => setIsHelpModalOpen(true)} />

      <main className="relative z-10 flex w-full flex-1 flex-col items-center justify-center gap-6 overflow-y-auto bg-surface-container-lowest px-6 py-6">
        <section
          aria-label="가게 인식표 스캔 영역"
          className="relative aspect-square w-full max-w-[280px]"
        >
          <div className="relative h-full w-full overflow-hidden rounded-2xl shadow-[0_12px_30px_rgba(0,0,0,0.18)]">
            <video
              ref={videoRef}
              aria-label="가게 인식표 스캔 카메라"
              className="absolute inset-0 h-full w-full object-cover"
              muted
              playsInline
              autoPlay
            />
            <span className="absolute left-0 top-0 z-20 size-10 rounded-tl-xl border-l-[8px] border-t-[8px] border-primary-container" />
            <span className="absolute right-0 top-0 z-20 size-10 rounded-tr-xl border-r-[8px] border-t-[8px] border-primary-container" />
            <span className="absolute bottom-0 left-0 z-20 size-10 rounded-bl-xl border-b-[8px] border-l-[8px] border-primary-container" />
            <span className="absolute bottom-0 right-0 z-20 size-10 rounded-br-xl border-b-[8px] border-r-[8px] border-primary-container" />
            <div className="qr-scan-line absolute left-0 right-0 z-30 h-1 bg-primary-container shadow-[0_0_15px_#5a19de]" />
            <div className="absolute inset-0 z-10 rounded-2xl border-4 border-transparent bg-transparent" />
          </div>
        </section>

        <button
          type="button"
          onClick={handleSwitchCamera}
          className="mb-2 flex min-h-14 w-full max-w-[240px] items-center justify-center gap-2 rounded-full border-2 border-primary-container bg-surface-container-lowest px-6 py-3 text-[20px] font-extrabold text-primary-container shadow-[0_6px_16px_rgba(90,25,222,0.12)] transition-all duration-150 hover:bg-primary-fixed active:scale-95"
        >
          <CameraSwitchIcon />
          카메라 바꾸기
        </button>

        <section className="w-full max-w-md rounded-[24px] bg-primary-container px-6 py-5 text-center shadow-[0_12px_28px_rgba(90,25,222,0.25)]">
          <div className="mx-auto mb-3 flex size-16 items-center justify-center rounded-full bg-white/15 text-white">
            <QRScannerIcon />
          </div>
          <h2 className="text-[28px] font-extrabold leading-9 text-white">
            가게 인식표를 맞춰주세요!
          </h2>
        </section>
      </main>

      {isHelpModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="qr-help-title"
          className="absolute inset-0 z-[60] flex items-center justify-center bg-black/50 px-6"
        >
          <div className="flex min-h-[420px] w-full max-w-sm flex-col justify-center rounded-[28px] bg-surface-container-lowest px-6 py-9 text-center shadow-2xl">
            <h2
              id="qr-help-title"
              className="translate-y-4 text-[30px] font-extrabold leading-10 text-on-surface"
            >
              가게 인식표 도움말
            </h2>
            <img
              src={qrHelpImage}
              alt="가게 인식표 예시"
              className="mx-auto mt-6 h-auto w-full max-w-[220px] rounded-2xl object-contain shadow-lg"
            />
            <p className="mt-5 whitespace-nowrap text-[18px] font-extrabold leading-7 text-primary">
              보라색 네모에 맞게 카메라를 대주세요!
            </p>
            <button
              type="button"
              onClick={() => setIsHelpModalOpen(false)}
              className="mt-6 w-full rounded-2xl bg-primary-container px-5 py-4 text-[22px] font-extrabold text-on-primary"
            >
              해볼게요
            </button>
          </div>
        </div>
      )}

      {scanResult && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="qr-scan-result-title"
          className="absolute inset-0 z-[70] flex items-center justify-center bg-black/60 px-6"
        >
          <div className="flex min-h-[220px] w-full max-w-sm flex-col items-center justify-center rounded-[28px] bg-surface-container-lowest px-6 py-6 text-center shadow-2xl">
            <h2
              id="qr-scan-result-title"
              className="text-[30px] font-extrabold leading-10 text-on-surface"
            >
              <span className="text-primary">{scanResult.storeName}</span>입니다🎉
            </h2>
            <button
              type="button"
              onClick={() => navigate(scanResult.orderPath)}
              className="mt-12 w-full rounded-2xl bg-primary-container px-5 py-4 text-[22px] font-extrabold text-on-primary shadow-lg transition-transform duration-150 active:scale-95"
            >
              주문하기
            </button>
          </div>
        </div>
      )}

      {scanError && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="qr-scan-error-title"
          className="absolute inset-0 z-[70] flex items-center justify-center bg-black/60 px-6"
        >
          <div className="flex min-h-[300px] w-full max-w-sm flex-col items-center justify-center rounded-[28px] bg-surface-container-lowest px-6 py-8 text-center shadow-2xl">
            <h2
              id="qr-scan-error-title"
              className="text-[30px] font-extrabold leading-10 text-on-surface"
            >
              가게 인식표가
              <br />
              올바르지 않아요 😞
            </h2>
            <p className="mt-4 text-[20px] font-bold leading-7 text-on-surface-variant">
              직원에게 문의해주세요!
            </p>
            <button
              type="button"
              onClick={handleRetryScan}
              className="mt-8 w-full rounded-2xl bg-primary-container px-5 py-4 text-[22px] font-extrabold text-on-primary shadow-lg transition-transform duration-150 active:scale-95"
            >
              다시 하기
            </button>
          </div>
        </div>
      )}
    </MobileLayout>
  );
};

export default QRScanPage;
