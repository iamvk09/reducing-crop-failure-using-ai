"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  GroundedContext,
  resolveGroundedAnswer,
  AssistantResponse,
} from "@shared/services/assistantEngine";

interface VoiceAssistantProps {
  context: GroundedContext;
  language: string;
  isOpen: boolean;
  onClose: () => void;
  onConfirmAction?: (actionType: string, payload?: any) => Promise<void>;
}

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  spokenText?: string;
  timestamp: string;
  sourceContext?: any;
  suggestedFollowUps?: string[];
}

export const VoiceAssistantPanel: React.FC<VoiceAssistantProps> = ({
  context,
  language,
  isOpen,
  onClose,
  onConfirmAction,
}) => {
  // Initial welcome message localized to the active language
  const getInitialMessage = (lang: string): Message => {
    const welcomeTexts: Record<string, { text: string; spoken: string; prompts: string[] }> = {
      hi: {
        text: "🌾 **नमस्ते! मैं आपका एआई फसल सहायक हूँ।**\n\nमैं आपकी फसल के जोखिम, मौसम, सेंटिनल-2 उपग्रह और मॉडल सलाह पर आधारित जानकारी प्रदान कर सकता हूँ।",
        spoken: "नमस्ते! मैं आपका एआई फसल सहायक हूँ। अपनी फसल के जोखिम या मौसम के बारे में पूछें।",
        prompts: ["मेरी फसल का जोखिम क्या है?", "यह जोखिम क्यों है?", "लाइव मौसम क्या है?", "उपग्रह क्या दिखाता है?"],
      },
      mr: {
        text: "🌾 **नमस्कार! मी तुमचा एआय पीक सहाय्यक आहे.**\n\nमी तुमच्या पिकाचा धोका, हवामान, उपग्रह निरीक्षणे आणि कृषी सल्ल्याबद्दल खरी माहिती देऊ शकतो.",
        spoken: "नमस्कार! मी तुमचा एआय पीक सहाय्यक आहे. पिकाचा धोका किंवा हवामानाबद्दल विचारा.",
        prompts: ["माझ्या पिकाचा धोका काय आहे?", "हा धोका का आहे?", "सध्याचे हवामान काय आहे?", "उपग्रह काय दर्शवतो?"],
      },
      bn: {
        text: "🌾 **নমস্কার! আমি আপনার এআই ফসল সহকারী।**\n\nআমি আপনার ফসলের ক্ষতির ঝুঁকি, আবহাওয়া এবং উপগ্রহ তথ্য সম্পর্কে প্রশ্নের উত্তর দিতে পারি।",
        spoken: "নমস্কার! আমি আপনার এআই ফসল সহকারী। ফসলের ঝুঁকি বা আবহাওয়া সম্পর্কে জিজ্ঞাসা করুন।",
        prompts: ["আমার ফসলের ঝুঁকি কত?", "এই ঝুঁকির কারণ কি?", "বর্তমান আবহাওয়া কি?", "উপগ্রহ কি দেখাচ্ছে?"],
      },
      te: {
        text: "🌾 **నమస్కారం! నేను మీ AI పంట సహాయకుడిని.**\n\nనేను మీ పంట నష్ట ప్రమాదం, వాతావరణం మరియు ఉపగ్రహ పరిశీలనల గురించి సమాధానాలు ఇవ్వగలను.",
        spoken: "నమస్కారం! నేను మీ AI పంట సహాయకుడిని. పంట ప్రమాదం లేదా వాతావరణం గురించి అడగండి.",
        prompts: ["నా పంట నష్ట ప్రమాదం ఎంత?", "ఈ ప్రమాదం ఎందుకు?", "ప్రస్తుత వాతావరణం ఏమిటి?", "ఉపగ్రహం ఏమి చూపిస్తుంది?"],
      },
      ta: {
        text: "🌾 **வணக்கம்! நான் உங்கள் AI பயிர் உதவியாளர்.**\n\nபயிர் இழப்பு அபாயம், வானிலை மற்றும் செயற்கைக்கோள் தரவுகள் குறித்து நான் தகவல்களை வழங்க முடியும்.",
        spoken: "வணக்கம்! நான் உங்கள் AI பயிர் உதவியாளர். பயிர் அபாயம் அல்லது வானிலை குறித்து கேளுங்கள்.",
        prompts: ["என் பயிர் அபாயம் என்ன?", "இந்த அபாயம் ஏன்?", "தற்போதைய வானிலை என்ன?", "செயற்கைக்கோள் என்ன காட்டுகிறது?"],
      },
      kn: {
        text: "🌾 **ನಮಸ್ಕಾರ! ನಾನು ನಿಮ್ಮ AI ಬೆಳೆ ಸಹಾಯಕ.**\n\nನಿಮ್ಮ ಬೆಳೆ ಹಾನಿಯ ಅಪಾಯ, ಹವಾಮಾನ ಮತ್ತು ಉಪಗ್ರಹ ವೀಕ್ಷಣೆಗಳ ಬಗ್ಗೆ ನಾನು ಮಾಹಿತಿ ನೀಡಬಲ್ಲೆ.",
        spoken: "ನಮಸ್ಕಾರ! ನಾನು ನಿಮ್ಮ AI ಬೆಳೆ ಸಹಾಯಕ. ಬೆಳೆ ಅಪಾಯ ಅಥವಾ ಹವಾಮಾನದ ಬಗ್ಗೆ ಕೇಳಿ.",
        prompts: ["ನನ್ನ ಬೆಳೆ ಅಪಾಯ ಎಷ್ಟು?", "ಈ ಅಪಾಯ ಏಕೆ?", "ಲೈವ್ ಹವಾಮಾನ ಏನು?", "ಉಪಗ್ರಹ ಏನು ತೋರಿಸುತ್ತದೆ?"],
      },
      gu: {
        text: "🌾 **નમસ્તે! હું તમારો AI પાક સહાયક છું.**\n\nહું તમારા પાકના જોખમ, હવામાન અને ઉપગ્રહ નિરીક્ષણો વિશે માહિતી આપી શકું છું.",
        spoken: "નમસ્તે! હું તમારો AI પાક સહાયક છું. પાક જોખમ અથવા હવામાન વિશે પૂછો.",
        prompts: ["મારા પાકનું જોખમ કેટલું છે?", "આ જોખમ કેમ છે?", "લાઇવ હવામાન શું છે?", "ઉપગ્રહ શું બતાવે છે?"],
      },
      en: {
        text: "🌾 **Hello! I am your AI Crop Assistant.**\n\nI can answer questions about your current crop failure risk, weather telemetry, Sentinel-2 observations, and SHAP feature drivers grounded directly in your farm's verified data.",
        spoken: "Hello! I am your AI Crop Assistant. Ask me about your crop failure risk, weather, or satellite observations.",
        prompts: [
          "What is my current crop-failure risk?",
          "Why did the model predict this risk?",
          "What does my latest Sentinel-2 observation show?",
          "What is my latest weather?",
        ],
      },
    };

    const conf = welcomeTexts[lang] || welcomeTexts.en;
    return {
      id: "initial-welcome",
      sender: "assistant",
      text: conf.text,
      spokenText: conf.spoken,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      suggestedFollowUps: conf.prompts,
    };
  };

  const [messages, setMessages] = useState<Message[]>([getInitialMessage(language)]);

  // Update initial message when language changes if no conversation has taken place yet
  useEffect(() => {
    if (messages.length === 1 && messages[0].id === "initial-welcome") {
      setMessages([getInitialMessage(language)]);
    }
  }, [language]);

  const [inputQuery, setInputQuery] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(true);
  const [synthesisSupported, setSynthesisSupported] = useState(true);
  const [recognitionError, setRecognitionError] = useState<string | null>(null);
  const [confirmingAction, setConfirmingAction] = useState<{
    actionType: string;
    description: string;
  } | null>(null);

  const recognitionRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const transcriptAccumulatorRef = useRef<string>("");
  const hasSubmittedRef = useRef<boolean>(false);
  const handleSendQueryRef = useRef<(q?: string) => void>(() => {});

  // Keep latest sendQuery function reference up to date for speech completion callbacks
  useEffect(() => {
    handleSendQueryRef.current = handleSendQuery;
  });

  // Auto-scroll on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Check speech synthesis support on mount and cleanup on unmount
  useEffect(() => {
    if (typeof window !== "undefined") {
      setSynthesisSupported("speechSynthesis" in window);
      const hasSpeechRecognition =
        "SpeechRecognition" in window || "webkitSpeechRecognition" in window;
      setSpeechSupported(hasSpeechRecognition);
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (_) {}
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Map app language code to speech locale
  const getSpeechLocale = (langCode: string): string => {
    const localeMap: Record<string, string> = {
      en: "en-IN",
      hi: "hi-IN",
      mr: "mr-IN",
      bn: "bn-IN",
      te: "te-IN",
      ta: "ta-IN",
      kn: "kn-IN",
      gu: "gu-IN",
    };
    return localeMap[langCode] || "en-IN";
  };

  // Localized UI strings for Assistant Panel
  const panelTexts: Record<string, {
    headerTitle: string;
    groundedBadge: string;
    noFarmSelected: string;
    stopSpeech: string;
    listenReply: string;
    confirmTitle: string;
    cancel: string;
    confirmExecute: string;
    actionConfirmed: string;
    actionFailed: string;
    micTooltipListening: string;
    micTooltipReady: string;
    placeholderListening: string;
    placeholderReady: string;
    sendBtn: string;
    statusListening: string;
    statusSpeaking: string;
    statusReady: string;
    apiUnavailable: string;
    voiceErrorTyping: string;
    micListening: string;
    micReady: string;
    errUnsupported: string;
    errPermission: string;
    errNetwork: string;
    errNoSpeech: string;
    errGeneric: string;
  }> = {
    hi: {
      headerTitle: "एआई फसल सहायक",
      groundedBadge: "सत्यापित एमवीपी",
      noFarmSelected: "कोई खेत चयनित नहीं (जिला मार्गदर्शिका सक्रिय)",
      stopSpeech: "⏹️ आवाज़ रोकें",
      listenReply: "🔊 उत्तर सुनें",
      confirmTitle: "⚠️ पुष्टि आवश्यक है",
      cancel: "रद्द करें",
      confirmExecute: "पुष्टि करें और चलाएं",
      actionConfirmed: "कार्रवाई सफलतापूर्वक निष्पादित की गई:",
      actionFailed: "कार्रवाई विफल रही:",
      micTooltipListening: "सुन रहा हूँ... रोकने के लिए क्लिक करें",
      micTooltipReady: "बोलने के लिए माइक दबाएं",
      placeholderListening: "सुन रहा हूँ... अब बोलें (समाप्त होने पर स्वतः भेजा जाएगा)",
      placeholderReady: "जोखिम, शाप, मौसम, उपग्रह के बारे में पूछें...",
      sendBtn: "भेजें",
      statusListening: "● आपकी आवाज़ सुन रहा हूँ...",
      statusSpeaking: "🔊 उत्तर बोलकर बता रहा हूँ...",
      statusReady: "तैयार (आवाज़ और टाइपिंग समर्थन)",
      apiUnavailable: "⚠️ वॉइस एपीआई अनुपलब्ध (टाइपिंग सक्रिय)",
      voiceErrorTyping: "⚠️ वॉइस सूचना (टाइपिंग का उपयोग करें)",
      micListening: "🎙️ माइक्रोफ़ोन सक्रिय है...",
      micReady: "🎙️ माइक तैयार (या नीचे टाइप करें)",
      errUnsupported: "इस ब्राउज़र में स्पीच रिकग्निशन समर्थित नहीं है। कृपया नीचे टाइप करें।",
      errPermission: "माइक्रोफ़ोन अनुमति अस्वीकृत। कृपया ब्राउज़र में अनुमति दें या टाइप करें।",
      errNetwork: "स्पीच नेटवर्क सेवा त्रुटि (ब्राउज़र वॉइस सर्वर से कनेक्शन)। कृपया नीचे टाइप करें।",
      errNoSpeech: "कोई आवाज़ नहीं पहचानी गई। कृपया पुनः बोलें या टाइप करें।",
      errGeneric: "स्पीच रिकग्निशन सूचना। आप नीचे टाइप कर सकते हैं।",
    },
    en: {
      headerTitle: "AI Crop Assistant",
      groundedBadge: "Grounded MVP",
      noFarmSelected: "No farm selected (District Guide Active)",
      stopSpeech: "⏹️ Stop Speech",
      listenReply: "🔊 Listen to reply",
      confirmTitle: "⚠️ Confirmation Required",
      cancel: "Cancel",
      confirmExecute: "Confirm & Execute",
      actionConfirmed: "Action Confirmed and Executed:",
      actionFailed: "Action Failed:",
      micTooltipListening: "Listening... Click to stop",
      micTooltipReady: "Speak your question",
      placeholderListening: "Listening... Speak now (auto-sends on finish)",
      placeholderReady: "Ask about risk, SHAP, weather, NDVI...",
      sendBtn: "Send",
      statusListening: "● Listening for voice...",
      statusSpeaking: "🔊 Speaking answer aloud...",
      statusReady: "Ready (Voice & Typed Support)",
      apiUnavailable: "⚠️ Voice API unavailable (Typing active)",
      voiceErrorTyping: "⚠️ Voice notice (Typing active)",
      micListening: "🎙️ Microphone listening...",
      micReady: "🎙️ Mic ready (or type below)",
      errUnsupported: "Speech recognition is not supported in this browser. Please use the text input below.",
      errPermission: "Microphone access was denied. Please allow microphone permissions in your browser or type your question.",
      errNetwork: "Browser speech recognition service network error. Please type your question in the text box below.",
      errNoSpeech: "No speech detected. Please try speaking again or type your question.",
      errGeneric: "Speech recognition notice. You can type your query in the text box.",
    },
  };

  const currentPanelText = panelTexts[language] || panelTexts.en;

  // Toggle Speech-to-Text
  const handleToggleListening = () => {
    setRecognitionError(null);

    if (isListening) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (_) {}
      }
      setIsListening(false);

      // If user manually stopped and we have a final transcript not yet submitted, auto-submit once
      const finalAccumulated = transcriptAccumulatorRef.current.trim();
      if (finalAccumulated && !hasSubmittedRef.current) {
        hasSubmittedRef.current = true;
        transcriptAccumulatorRef.current = "";
        handleSendQueryRef.current(finalAccumulated);
      }
      return;
    }

    if (typeof window === "undefined") return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setRecognitionError(currentPanelText.errUnsupported);
      setSpeechSupported(false);
      return;
    }

    try {
      // Reset accumulator and submission guard for new utterance
      transcriptAccumulatorRef.current = "";
      hasSubmittedRef.current = false;

      const recognition = new SpeechRecognition();
      recognition.lang = getSpeechLocale(language);
      recognition.continuous = false;
      recognition.interimResults = true;

      recognition.onstart = () => {
        setIsListening(true);
        setRecognitionError(null);
      };

      recognition.onresult = (event: any) => {
        let interimTranscript = "";
        let finalTranscript = "";

        for (let i = 0; i < event.results.length; ++i) {
          const res = event.results[i];
          if (res.isFinal) {
            finalTranscript += res[0].transcript;
          } else {
            interimTranscript += res[0].transcript;
          }
        }

        const combined = (finalTranscript || interimTranscript).trim();
        if (combined) {
          setInputQuery(combined);
        }
        if (finalTranscript.trim()) {
          transcriptAccumulatorRef.current = finalTranscript.trim();
        } else if (interimTranscript.trim()) {
          transcriptAccumulatorRef.current = interimTranscript.trim();
        }
      };

      recognition.onerror = (event: any) => {
        console.warn("Speech recognition error:", event.error);
        setIsListening(false);
        if (event.error === "not-allowed" || event.error === "permission-denied") {
          setRecognitionError(currentPanelText.errPermission);
        } else if (event.error === "network") {
          setRecognitionError(currentPanelText.errNetwork);
        } else if (event.error === "no-speech") {
          setRecognitionError(currentPanelText.errNoSpeech);
        } else {
          setRecognitionError(`${currentPanelText.errGeneric} (${event.error})`);
        }
      };

      const triggerAutoSubmit = () => {
        setIsListening(false);
        const textToSend = transcriptAccumulatorRef.current.trim();
        if (textToSend && !hasSubmittedRef.current) {
          hasSubmittedRef.current = true;
          transcriptAccumulatorRef.current = "";
          handleSendQueryRef.current(textToSend);
        }
      };

      if ("onspeechend" in recognition) {
        recognition.onspeechend = () => {
          // Trigger stop which leads to onend
          try {
            recognition.stop();
          } catch (_) {}
        };
      }

      recognition.onend = () => {
        triggerAutoSubmit();
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err: any) {
      console.error("Failed to start speech recognition:", err);
      setIsListening(false);
      setRecognitionError(err.message || "Failed to initialize microphone.");
    }
  };

  // Browser Text-to-Speech
  const handleSpeak = (text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setRecognitionError("Speech synthesis is unavailable in this environment.");
      return;
    }

    window.speechSynthesis.cancel();

    if (isSpeaking) {
      setIsSpeaking(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    const targetLocale = getSpeechLocale(language);
    utterance.lang = targetLocale;
    utterance.rate = 0.95;
    utterance.pitch = 1.0;

    // Pick closest installed browser voice matching the selected language locale
    try {
      const voices = window.speechSynthesis.getVoices();
      if (voices && voices.length > 0) {
        const exactMatch = voices.find((v) => v.lang === targetLocale || v.lang.replace(/_/g, "-") === targetLocale);
        const langPrefixMatch = voices.find((v) => v.lang.startsWith(language) || v.lang.toLowerCase().includes(language));
        if (exactMatch) {
          utterance.voice = exactMatch;
        } else if (langPrefixMatch) {
          utterance.voice = langPrefixMatch;
        }
      }
    } catch (_) {}

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    window.speechSynthesis.speak(utterance);
  };

  const handleStopSpeaking = () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  };

  // Submit query
  const handleSendQuery = (customQuery?: string) => {
    const q = (customQuery || inputQuery).trim();
    if (!q) return;

    handleStopSpeaking();

    const userMsg: Message = {
      id: `usr-${Date.now()}`,
      sender: "user",
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuery("");
    setRecognitionError(null);

    // Intent engine resolution
    const resp: AssistantResponse = resolveGroundedAnswer(q, context);

    const assistantMsg: Message = {
      id: `ast-${Date.now()}`,
      sender: "assistant",
      text: resp.answerText,
      spokenText: resp.spokenText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      sourceContext: resp.sourceContext,
      suggestedFollowUps: resp.suggestedFollowUps,
    };

    setMessages((prev) => [...prev, assistantMsg]);

    // Automatically speak response if synthesis supported and user used voice
    if (synthesisSupported && isListening) {
      handleSpeak(resp.spokenText);
    }
  };

  // Safe action trigger request with confirmation modal
  const handleRequestAction = (actionType: string, description: string) => {
    setConfirmingAction({ actionType, description });
  };

  const handleExecuteConfirmedAction = async () => {
    if (!confirmingAction || !onConfirmAction) return;
    try {
      await onConfirmAction(confirmingAction.actionType);
      setMessages((prev) => [
        ...prev,
        {
          id: `act-${Date.now()}`,
          sender: "assistant",
          text: `✅ **Action Confirmed and Executed:** ${confirmingAction.description}`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: "assistant",
          text: `❌ **Action Failed:** ${err.message}`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setConfirmingAction(null);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-label="AI Crop Assistant Panel"
      className="fixed bottom-4 right-4 z-50 w-full max-w-md bg-[#121815] border border-[#23352a] rounded-2xl shadow-2xl flex flex-col h-[620px] max-h-[85vh] text-gray-100 overflow-hidden"
    >
      {/* Header */}
      <div className="bg-[#0c1510] border-b border-[#23352a] p-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-emerald-900/60 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
            🎙️
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              {currentPanelText.headerTitle}
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono">
                {currentPanelText.groundedBadge}
              </span>
            </h3>
            <p className="text-[10px] text-gray-400">
              {context.mode === "district" && context.districtContext
                ? `District Guide: ${context.districtContext.district} (${context.districtContext.year} ${context.districtContext.season} - ${context.districtContext.crop})`
                : context.farm
                ? `Field: ${context.farm.name} (${context.crop?.crop ? `${context.crop.crop} (${context.crop.season || "Active"})` : "No active crop cycle"})`
                : currentPanelText.noFarmSelected}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isSpeaking && (
            <button
              onClick={handleStopSpeaking}
              className="text-xs px-2 py-1 rounded bg-amber-900/50 text-amber-300 border border-amber-700/50 hover:bg-amber-800 transition"
              title="Stop audio playback"
            >
              {currentPanelText.stopSpeech}
            </button>
          )}
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-lg p-1 rounded-lg hover:bg-[#17221b] transition"
            aria-label="Close assistant"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5 text-xs">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${
              m.sender === "user" ? "items-end" : "items-start"
            }`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 ${
                m.sender === "user"
                  ? "bg-emerald-700 text-white font-medium rounded-tr-none shadow"
                  : "bg-[#17221b] border border-[#23352a] text-gray-200 rounded-tl-none space-y-2"
              }`}
            >
              <div className="whitespace-pre-line leading-relaxed">{m.text}</div>

              {/* Speech Playback button on assistant replies */}
              {m.sender === "assistant" && m.spokenText && synthesisSupported && (
                <div className="pt-1.5 flex items-center justify-between border-t border-[#23352a]/60">
                  <button
                    onClick={() => handleSpeak(m.spokenText!)}
                    className="inline-flex items-center gap-1 text-[11px] text-emerald-400 hover:text-emerald-300 font-semibold"
                  >
                    {currentPanelText.listenReply}
                  </button>
                  <span className="text-[9px] text-gray-400 font-mono">{m.timestamp}</span>
                </div>
              )}
            </div>

            {/* Suggested Follow-Ups */}
            {m.suggestedFollowUps && m.suggestedFollowUps.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5 max-w-[90%]">
                {m.suggestedFollowUps.map((sug, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendQuery(sug)}
                    className="text-[10px] px-2.5 py-1 rounded-full bg-[#1b2b22] border border-[#2a4535] text-emerald-300 hover:bg-[#23382c] transition text-left"
                  >
                    💡 {sug}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Confirmation Modal Overlay for Action Guard */}
      {confirmingAction && (
        <div className="p-3 bg-amber-950/90 border-t border-amber-700/60 text-amber-200 text-xs space-y-2">
          <p className="font-bold flex items-center gap-1.5">
            {currentPanelText.confirmTitle}
          </p>
          <p>{confirmingAction.description}</p>
          <div className="flex gap-2 justify-end pt-1">
            <button
              onClick={() => setConfirmingAction(null)}
              className="px-2.5 py-1 rounded bg-[#17221b] text-gray-300 hover:bg-[#23352a] text-[11px]"
            >
              {currentPanelText.cancel}
            </button>
            <button
              onClick={handleExecuteConfirmedAction}
              className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white font-bold text-[11px]"
            >
              {currentPanelText.confirmExecute}
            </button>
          </div>
        </div>
      )}

      {/* Recognition status / error alerts */}
      {recognitionError && (
        <div className="px-3 py-1.5 bg-red-950/80 border-t border-red-800 text-red-200 text-[11px] flex items-center justify-between">
          <span>{recognitionError}</span>
          <button
            onClick={() => setRecognitionError(null)}
            className="text-red-400 hover:text-white ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {/* Input Tray */}
      <div className="p-3 bg-[#0c1510] border-t border-[#23352a] space-y-2">
        <div className="flex items-center gap-2">
          {/* Microphone Button */}
          <button
            onClick={handleToggleListening}
            className={`p-2.5 rounded-xl border font-bold transition flex items-center justify-center shrink-0 ${
              isListening
                ? "bg-red-600 border-red-400 text-white animate-pulse"
                : "bg-[#17221b] border-[#23352a] text-emerald-400 hover:bg-[#23382c]"
            }`}
            title={isListening ? currentPanelText.micTooltipListening : currentPanelText.micTooltipReady}
            aria-label="Microphone Voice Input"
          >
            {isListening ? "🔴" : "🎙️"}
          </button>

          {/* Text input fallback */}
          <input
            type="text"
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendQuery()}
            placeholder={
              isListening
                ? currentPanelText.placeholderListening
                : currentPanelText.placeholderReady
            }
            className="flex-1 bg-[#17221b] border border-[#23352a] rounded-xl px-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 transition"
          />

          {/* Send Button */}
          <button
            onClick={() => handleSendQuery()}
            disabled={!inputQuery.trim()}
            className="px-3 py-2 rounded-xl bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:hover:bg-emerald-700 text-white font-bold text-xs transition"
          >
            {currentPanelText.sendBtn}
          </button>
        </div>

        {/* State Indicators */}
        <div className="flex items-center justify-between text-[10px] text-gray-400 px-1">
          <span>
            {isListening ? (
              <span className="text-red-400 font-semibold animate-pulse">
                {currentPanelText.statusListening}
              </span>
            ) : isSpeaking ? (
              <span className="text-amber-400 font-semibold">
                {currentPanelText.statusSpeaking}
              </span>
            ) : (
              currentPanelText.statusReady
            )}
          </span>
          <span className="text-gray-400">
            {!speechSupported
              ? currentPanelText.apiUnavailable
              : isListening
              ? currentPanelText.micListening
              : recognitionError
              ? currentPanelText.voiceErrorTyping
              : currentPanelText.micReady}
          </span>
        </div>
      </div>
    </div>
  );
};
