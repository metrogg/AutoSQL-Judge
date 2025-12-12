const { createApp, ref, onMounted, onUnmounted } = Vue;

createApp({
  setup() {
    const currentDataset = ref('student_scores');
    const totalScore = ref(0);
    const currentUser = ref(null);
    const currentQuestion = ref(null);
    const loading = ref(false);
    const loadingSource = ref('');

    const userSql = ref('');
    const submitting = ref(false);
    const judgeResult = ref(null);
    const schemaPreview = ref({});

    const hasSubmitted = ref(false);
    const answerText = ref('');
    const answerLoading = ref(false);
    const explainText = ref('');
    const explainLoading = ref(false);

    const llmHint = ref('');
    const chatMessages = ref([]);

    const aiPanelVisible = ref(false);
    const aiMessages = ref([]);
    const aiInput = ref('');
    const aiTyping = ref(false);
    const aiChatBody = ref(null);
    const aiPanelRight = ref(24);
    const aiPanelBottom = ref(24);
    const aiDragging = ref(false);
    const dragStart = ref({ x: 0, y: 0 });
    const dragStartPos = ref({ right: 24, bottom: 24 });

    const toasts = ref([]);
    const editor = ref(null);
    const useMonaco = ref(false);
    const lastAiClickTs = ref(0);

    const leftCollapsed = ref(false);
    const rightCollapsed = ref(false);
    const isResizing = ref(false);

    const showToast = (message, type = 'info') => {
      const icons = {
        success: 'bi-check-circle-fill',
        error: 'bi-x-circle-fill',
        info: 'bi-info-circle-fill',
      };
      const toast = { message, type, icon: icons[type] || icons.info };
      toasts.value.push(toast);
      setTimeout(() => {
        const idx = toasts.value.indexOf(toast);
        if (idx > -1) toasts.value.splice(idx, 1);
      }, 3000);
    };

    const scrollAiChatToBottom = () => {
      setTimeout(() => {
        if (aiChatBody.value) {
          aiChatBody.value.scrollTop = aiChatBody.value.scrollHeight;
        }
      }, 50);
    };

    const typewriterEffect = async (fullText) => {
      const msgIndex = aiMessages.value.length;
      aiMessages.value.push({ role: 'assistant', content: '', typing: true });
      scrollAiChatToBottom();

      const chars = fullText.split('');
      const speed = 20;

      for (let i = 0; i < chars.length; i += 1) {
        aiMessages.value[msgIndex].content += chars[i];
        if (i % 5 === 0) scrollAiChatToBottom();
        // eslint-disable-next-line no-await-in-loop
        await new Promise((resolve) => setTimeout(resolve, speed));
      }

      aiMessages.value[msgIndex].typing = false;
      scrollAiChatToBottom();
    };

    const fetchCurrentUser = async () => {
      try {
        const res = await axios.get('/api/auth/me');
        if (res.data.status === 'success' && res.data.data) {
          currentUser.value = res.data.data;
          totalScore.value = res.data.data.total_score || 0;
        } else {
          currentUser.value = null;
          totalScore.value = 0;
        }
      } catch (err) {
        // 静默失败即可
        // eslint-disable-next-line no-console
        console.error('获取当前用户失败', err);
      }
    };

    const fetchSchemaPreview = async () => {
      try {
        const res = await axios.get('/api/dataset/preview', {
          params: { dataset_key: currentDataset.value },
        });
        if (res.data.status === 'success' && res.data.data) {
          schemaPreview.value = res.data.data.tables || {};
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('加载示例数据失败', err);
      }
    };

    const fetchQuestion = async (source = 'db', customHint = null) => {
      if (loading.value) return;

      if (source === 'llm') {
        const now = Date.now();
        if (now - lastAiClickTs.value < 5000) {
          showToast('AI 出题请求过于频繁，请稍后再试', 'error');
          return;
        }
        lastAiClickTs.value = now;
      }

      loading.value = true;
      loadingSource.value = source;

      judgeResult.value = null;
      userSql.value = '';
      hasSubmitted.value = false;
      answerText.value = '';
      explainText.value = '';

      if (editor.value) {
        editor.value.setValue('');
      }

      try {
        const params = { dataset_key: currentDataset.value, source };
        if (source === 'llm' && typeof customHint === 'string') {
          const trimmed = customHint.trim();
          if (trimmed) params.user_hint = trimmed;
        }
        const res = await axios.get('/api/question/generate', { params });
        if (res.data.status === 'success') {
          currentQuestion.value = res.data.data;
          showToast('题目加载成功', 'success');
        } else {
          showToast(res.data.msg || '获取题目失败', 'error');
        }
      } catch (err) {
        showToast('获取题目失败: ' + (err.response?.data?.msg || err.message), 'error');
      } finally {
        loading.value = false;
        loadingSource.value = '';
      }
    };

    const sendChat = async () => {
      const text = (llmHint.value || '').trim();
      if (!text || loading.value) return;
      chatMessages.value.push({ role: 'user', content: text });
      await fetchQuestion('llm', text);
      if (currentQuestion.value) {
        chatMessages.value.push({
          role: 'assistant',
          content: `已为你生成一题：《${currentQuestion.value.title}》`,
        });
      }
      llmHint.value = '';
    };

    const submitSolution = async () => {
      if (!currentQuestion.value || !userSql.value) return;
      submitting.value = true;
      try {
        const res = await axios.post('/api/judge/submit', {
          question_id: currentQuestion.value.id,
          user_sql: userSql.value,
        });
        if (res.data.status === 'success') {
          judgeResult.value = res.data.data;
          hasSubmitted.value = true;

          if (res.data.data.total_score != null) {
            totalScore.value = res.data.data.total_score;
          } else if (res.data.data.result === 'Pass') {
            totalScore.value += res.data.data.score;
          }

          const r = res.data.data.result;
          if (r === 'Pass') showToast('恭喜！答案正确！', 'success');
          else if (r === 'Fail') showToast('结果不一致，请检查逻辑', 'error');
          else showToast('执行出错，请检查 SQL 语法', 'error');
        } else {
          showToast(res.data.msg || '判题失败', 'error');
        }
      } catch (err) {
        judgeResult.value = {
          result: 'Error',
          msg: err.response?.data?.msg || '系统错误',
          execution_time: 0,
        };
        showToast('判题失败：' + (err.response?.data?.msg || '系统错误'), 'error');
      } finally {
        submitting.value = false;
      }
    };

    const viewAnswer = async () => {
      if (!currentQuestion.value || answerLoading.value) return;
      if (!hasSubmitted.value) {
        showToast('请先提交一次你的解答', 'error');
        return;
      }
      if (!currentQuestion.value.allow_view_answer) {
        showToast('本题暂未开放查看标准答案', 'error');
        return;
      }
      answerLoading.value = true;
      try {
        const res = await axios.get('/api/question/answer', {
          params: { question_id: currentQuestion.value.id },
        });
        if (res.data.status === 'success' && res.data.data) {
          answerText.value = res.data.data.standard_sql || '';
          showToast('标准答案已显示', 'success');
        } else {
          showToast(res.data.msg || '获取标准答案失败', 'error');
        }
      } catch (err) {
        showToast('获取标准答案失败: ' + (err.response?.data?.msg || err.message), 'error');
      } finally {
        answerLoading.value = false;
      }
    };

    const buildHistoryText = () => {
      if (!aiMessages.value.length) return '';
      return aiMessages.value
        .map((m) => (m.role === 'user' ? '学生：' : 'AI：') + m.content)
        .join('\n');
    };

    const askExplain = async () => {
      if (!currentQuestion.value || !userSql.value) {
        showToast('请先写好并点击"运行"提交一次 SQL', 'error');
        return;
      }
      if (!judgeResult.value) {
        showToast('请先完成一次判题', 'error');
        return;
      }
      if (explainLoading.value) return;

      aiPanelVisible.value = true;
      showToast('AI 正在思考中...', 'info');

      const historyText = buildHistoryText();
      const baseMsg = judgeResult.value.msg || '';
      let combined = baseMsg;
      if (historyText) {
        combined = (baseMsg ? `${baseMsg}\n\n` : '') + '历史对话（学生与 AI）：\n' + historyText;
      }

      const userReqText =
        judgeResult.value.result === 'Pass'
          ? '请点评并拓展一下我刚才的 SQL 答案，告诉我做得好的地方和可以改进的地方，并梳理相关知识点。'
          : '请详细分析一下我刚才提交的 SQL 哪里有问题，应该如何修改，并帮我梳理相关的 SQL 知识点。';

      aiMessages.value.push({ role: 'user', content: userReqText });
      scrollAiChatToBottom();

      explainLoading.value = true;
      aiTyping.value = true;
      try {
        const payload = {
          question_id: currentQuestion.value.id,
          user_sql: userSql.value,
          result: judgeResult.value.result,
          judge_message:
            (combined ? `${combined}\n\n` : '') + '学生的请求：' + userReqText,
        };
        const res = await axios.post('/api/judge/explain', payload);
        aiTyping.value = false;
        if (res.data.status === 'success' && res.data.data) {
          const feedback = res.data.data.feedback || '';
          explainText.value = feedback;
          await typewriterEffect(feedback);
          showToast('AI 讲解完成', 'success');
        } else {
          showToast(res.data.msg || 'AI 讲解失败', 'error');
        }
      } catch (err) {
        aiTyping.value = false;
        showToast(
          'AI 讲解失败: ' + (err.response?.data?.msg || err.message),
          'error',
        );
      } finally {
        explainLoading.value = false;
      }
    };

    const sendAiChat = async () => {
      const text = (aiInput.value || '').trim();
      if (!text) return;
      if (!currentQuestion.value || !userSql.value) {
        showToast('请先针对当前题目写 SQL 并点击"运行"', 'error');
        return;
      }
      if (!judgeResult.value) {
        showToast('请先完成一次判题', 'error');
        return;
      }
      if (explainLoading.value) return;

      aiPanelVisible.value = true;

      const historyText = buildHistoryText();
      const baseMsg = judgeResult.value.msg || '';
      let combined = baseMsg;
      if (historyText) {
        combined = (baseMsg ? `${baseMsg}\n\n` : '') + '历史对话（学生与 AI）：\n' + historyText;
      }
      combined = (combined ? `${combined}\n\n` : '') + '学生的最新提问：' + text;

      aiMessages.value.push({ role: 'user', content: text });
      aiInput.value = '';
      scrollAiChatToBottom();

      explainLoading.value = true;
      aiTyping.value = true;
      try {
        const payload = {
          question_id: currentQuestion.value.id,
          user_sql: userSql.value,
          result: judgeResult.value.result,
          judge_message: combined,
        };
        const res = await axios.post('/api/judge/explain', payload);
        aiTyping.value = false;
        if (res.data.status === 'success' && res.data.data) {
          const feedback = res.data.data.feedback || '';
          explainText.value = feedback;
          await typewriterEffect(feedback);
        } else {
          showToast(res.data.msg || 'AI 讲解失败', 'error');
        }
      } catch (err) {
        aiTyping.value = false;
        showToast(
          'AI 讲解失败: ' + (err.response?.data?.msg || err.message),
          'error',
        );
      } finally {
        explainLoading.value = false;
      }
    };

    const startDragAiPanel = (event) => {
      aiDragging.value = true;
      dragStart.value = { x: event.clientX, y: event.clientY };
      dragStartPos.value = {
        right: aiPanelRight.value,
        bottom: aiPanelBottom.value,
      };
    };

    const toggleLeftPanel = () => {
      leftCollapsed.value = !leftCollapsed.value;
    };

    const toggleRightPanel = () => {
      rightCollapsed.value = !rightCollapsed.value;
    };

    const startResize = (e) => {
      isResizing.value = true;
      e.preventDefault();
    };

    const handleWindowMouseMove = (event) => {
      if (aiDragging.value) {
        const dx = event.clientX - dragStart.value.x;
        const dy = event.clientY - dragStart.value.y;
        aiPanelRight.value = Math.max(0, dragStartPos.value.right - dx);
        aiPanelBottom.value = Math.max(0, dragStartPos.value.bottom - dy);
      }

      if (isResizing.value) {
        const container = document.querySelector('.main-layout');
        const left = document.querySelector('.left-panel');
        if (!container || !left) return;
        const containerWidth = container.offsetWidth;
        const newPercent = (event.clientX / containerWidth) * 100;
        if (newPercent > 20 && newPercent < 80) {
          left.style.width = `${newPercent}%`;
        }
      }
    };

    const handleWindowMouseUp = () => {
      aiDragging.value = false;
      isResizing.value = false;
    };

    const getResultIcon = (status) => {
      if (status === 'Pass') return 'bi-check-circle-fill';
      if (status === 'Fail') return 'bi-x-circle-fill';
      return 'bi-exclamation-triangle-fill';
    };

    const changeDataset = () => {
      showToast('当前 Demo 仅提供 student_scores 场景', 'info');
    };

    const loginOrRegister = async () => {
      const username = prompt('请输入用户名（至少 3 个字符）：');
      if (!username) return;
      const password = prompt('请输入密码（至少 4 个字符）：');
      if (!password) return;

      try {
        const res = await axios.post('/api/auth/login', { username, password });
        if (res.data.status === 'success') {
          currentUser.value = res.data.data;
          totalScore.value = res.data.data.total_score || 0;
          showToast('登录成功', 'success');
          return;
        }
      } catch (err) {
        const code = err.response?.data?.code;
        const msg = err.response?.data?.msg || '登录失败';
        if (code === 'USER_NOT_FOUND') {
          if (confirm(`${msg}，是否使用该账号直接注册？`)) {
            try {
              const resReg = await axios.post('/api/auth/register', {
                username,
                password,
              });
              if (resReg.data.status === 'success') {
                currentUser.value = resReg.data.data;
                totalScore.value = resReg.data.data.total_score || 0;
                showToast('注册并登录成功', 'success');
                return;
              }
            } catch (err2) {
              showToast(err2.response?.data?.msg || '注册失败', 'error');
              return;
            }
          }
        } else {
          showToast(msg, 'error');
          return;
        }
      }
    };

    const logout = async () => {
      try {
        await axios.post('/api/auth/logout');
        showToast('已退出登录', 'success');
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('退出登录失败', err);
      } finally {
        currentUser.value = null;
        totalScore.value = 0;
      }
    };

    onMounted(() => {
      if (window.require) {
        window.require.config({
          paths: {
            vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs',
          },
        });
        window.require(['vs/editor/editor.main'], () => {
          editor.value = monaco.editor.create(
            document.getElementById('monaco-editor'),
            {
              value: userSql.value,
              language: 'sql',
              theme: 'vs-dark',
              automaticLayout: true,
              fontSize: 14,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
            },
          );
          editor.value.onDidChangeModelContent(() => {
            userSql.value = editor.value.getValue();
          });
          useMonaco.value = true;
        });
      }

      window.addEventListener('mousemove', handleWindowMouseMove);
      window.addEventListener('mouseup', handleWindowMouseUp);

      fetchCurrentUser();
      fetchSchemaPreview();
      fetchQuestion();
    });

    onUnmounted(() => {
      window.removeEventListener('mousemove', handleWindowMouseMove);
      window.removeEventListener('mouseup', handleWindowMouseUp);
    });

    return {
      currentDataset,
      totalScore,
      currentUser,
      currentQuestion,
      loading,
      loadingSource,
      userSql,
      submitting,
      judgeResult,
      schemaPreview,
      hasSubmitted,
      answerText,
      answerLoading,
      explainText,
      explainLoading,
      llmHint,
      chatMessages,
      aiPanelVisible,
      aiMessages,
      aiInput,
      aiTyping,
      aiChatBody,
      aiPanelRight,
      aiPanelBottom,
      leftCollapsed,
      rightCollapsed,
      isResizing,
      useMonaco,
      toasts,
      fetchQuestion,
      sendChat,
      submitSolution,
      viewAnswer,
      askExplain,
      sendAiChat,
      startDragAiPanel,
      toggleLeftPanel,
      toggleRightPanel,
      startResize,
      changeDataset,
      loginOrRegister,
      logout,
      getResultIcon,
    };
  },
}).mount('#app');
