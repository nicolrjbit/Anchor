/**
 * 锚点平台状态机配置（与 Python anchor/state_machine.py 对齐）
 * 供前端或 Node 服务直接引用。
 */

export const STATES = {
  INIT: "INIT",
  SLOT_FILLING: "SLOT_FILLING",
  RISK_CLARIFY: "RISK_CLARIFY",
  CONVERGENCE: "CONVERGENCE",
};

export const StateMachineConfig = {
  currentState: STATES.INIT,

  transitions: {
    [STATES.INIT]: {
      onUserMessage: () => STATES.SLOT_FILLING,
    },
    [STATES.SLOT_FILLING]: {
      onCheckData: (slots, hasConflict) => {
        if (!slots.destination || !slots.days || !slots.anchor || !slots.tags?.length) {
          return STATES.SLOT_FILLING;
        }
        if (hasConflict) {
          return STATES.RISK_CLARIFY;
        }
        return STATES.CONVERGENCE;
      },
    },
    [STATES.RISK_CLARIFY]: {
      onUserConfirm: () => STATES.CONVERGENCE,
    },
  },
};

/** 必填四要素 */
export const REQUIRED_SLOTS = ["destination", "days", "anchor", "tags"];
