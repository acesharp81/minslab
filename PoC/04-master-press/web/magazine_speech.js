(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.MagazineSpeech = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function createController(options) {
    options = options || {};
    var synth = options.synthesis;
    var Utterance = options.Utterance;
    var onChange = typeof options.onChange === 'function' ? options.onChange : function () {};
    var defer = options.defer || function (callback) { setTimeout(callback, 0); };
    var segments = [];
    var cursor = 0;
    var current = null;
    var rate = 1.5;
    var runId = 0;
    var status = 'idle';
    var errorMessage = '';

    function supported() {
      return !!(synth && Utterance && typeof synth.speak === 'function');
    }

    function issueCount() {
      return segments.filter(function (segment) { return segment.kind === 'issue'; }).length;
    }

    function currentIssue() {
      if (status === 'completed') return issueCount();
      if (current && current.kind === 'issue') return Number(current.index || 0) + 1;
      if (current && current.kind === 'outro') return issueCount();
      return 0;
    }

    function snapshot() {
      return {
        status: status,
        issueCount: issueCount(),
        currentIssue: currentIssue(),
        segment: current,
        rate: rate,
        error: errorMessage
      };
    }

    function emit() {
      onChange(snapshot());
    }

    function koreanVoice() {
      if (!synth || typeof synth.getVoices !== 'function') return null;
      var voices = synth.getVoices() || [];
      var korean = voices.filter(function (voice) {
        return String(voice.lang || '').replace('_', '-').toLowerCase().indexOf('ko') === 0;
      });
      return korean.find(function (voice) { return voice.default; }) || korean[0] || null;
    }

    function speakNext(expectedRunId) {
      if (expectedRunId !== runId || status === 'idle') return;
      if (cursor >= segments.length) {
        current = null;
        status = 'completed';
        emit();
        return;
      }
      current = segments[cursor];
      var utterance = new Utterance(String(current.text || ''));
      var voice = koreanVoice();
      utterance.lang = voice && voice.lang ? voice.lang : 'ko-KR';
      utterance.rate = rate;
      if (voice) utterance.voice = voice;
      utterance.onstart = function () {
        if (expectedRunId !== runId) return;
        status = 'speaking';
        emit();
      };
      utterance.onend = function () {
        if (expectedRunId !== runId) return;
        cursor += 1;
        speakNext(expectedRunId);
      };
      utterance.onerror = function (event) {
        if (expectedRunId !== runId) return;
        errorMessage = event && event.error ? String(event.error) : '음성 재생 오류';
        status = 'error';
        emit();
      };
      synth.speak(utterance);
      emit();
    }

    function start(nextSegments) {
      if (!supported()) {
        status = 'unsupported';
        emit();
        return false;
      }
      segments = (nextSegments || []).filter(function (segment) {
        return segment && String(segment.text || '').trim();
      });
      if (!segments.length) {
        status = 'empty';
        emit();
        return false;
      }
      runId += 1;
      var expectedRunId = runId;
      cursor = 0;
      current = null;
      errorMessage = '';
      status = 'speaking';
      if (typeof synth.cancel === 'function') synth.cancel();
      emit();
      defer(function () { speakNext(expectedRunId); });
      return true;
    }

    function pause() {
      if (status !== 'speaking' || typeof synth.pause !== 'function') return false;
      synth.pause();
      status = 'paused';
      emit();
      return true;
    }

    function resume() {
      if (status !== 'paused' || typeof synth.resume !== 'function') return false;
      synth.resume();
      status = 'speaking';
      emit();
      return true;
    }

    function stop() {
      runId += 1;
      if (synth && typeof synth.cancel === 'function') synth.cancel();
      cursor = 0;
      current = null;
      errorMessage = '';
      status = 'idle';
      emit();
    }

    function setRate(value) {
      var parsed = Number(value);
      if ([1, 1.25, 1.5, 1.75, 2].indexOf(parsed) < 0) parsed = 1.5;
      rate = parsed;
      emit();
      return rate;
    }

    return {
      supported: supported,
      start: start,
      pause: pause,
      resume: resume,
      stop: stop,
      setRate: setRate,
      getState: snapshot
    };
  }

  return {createController: createController};
}));
