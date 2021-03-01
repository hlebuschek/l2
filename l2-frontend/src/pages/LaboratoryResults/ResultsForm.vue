<template>
  <fragment>
    <div class="root" ref="root">
      <table class="table table-bordered table-sm-pd">
        <thead>
        <tr>
          <th colspan="3">
            {{ research.title }}
          </th>
          <td class="cl-td">
            <button class="btn btn-blue-nb header-button" @click="clearAll" :disabled="confirmed">
              Очистить всё
            </button>
          </td>
        </tr>
        <tr class="table-header">
          <th style="width: 29%">Фракция</th>
          <th>Значение</th>
          <th style="width: 23%">Нормы М</th>
          <th style="width: 23%">Нормы Ж</th>
        </tr>
        </thead>
        <tbody>
        <tr v-for="r in result">
          <td>
            <label class="fraction-title" :for="`fraction-${r.fraction.pk}`">{{ r.fraction.title }}</label>
          </td>
          <td class="val">
            <input type="text" class="form-control result-field"
                   :class="[
                     r.fraction.units.length > 0 && 'with-units',
                     `isnorm_${r.norm}`,
                   ]"
                   :readonly="!loaded || confirmed"
                   @keyup.enter="moveFocusNext"
                   v-model="r.value" :id="`fraction-${r.fraction.pk}`" :data-x="Math.min(r.fraction.units.length, 9)">
            <div class="unit">{{ r.fraction.units }}</div>
          </td>
          <Ref :data="r.ref.m"/>
          <Ref :data="r.ref.f"/>
        </tr>
        <tr v-if="research.can_comment">
          <td><label class="fraction-title" for="result_comment">Комментарий</label></td>
          <td colspan="3">
            <textarea class="noresize form-control result-field"
                      v-autosize="comment" v-model="comment" id="result_comment"></textarea>
          </td>
        </tr>
        </tbody>
      </table>
    </div>
    <div class="bottom-buttons">
      <template v-if="loaded">
        <template v-if="!confirmed">
          <button class="btn btn-blue-nb btn-right" @click="saveAndConfirm()">
            Сохранить и подтвердить
          </button>
          <button class="btn btn-blue-nb btn-right" :disabled="!saved" @click="confirm()">
            Подтвердить
          </button>
          <button class="btn btn-blue-nb btn-right" @click="save()">
            Сохранить
          </button>
        </template>
        <template v-else>
          <button class="btn btn-blue-nb btn-right" :disabled="!allow_reset_confirm">
            Сброс подтверждения
          </button>
        </template>
      </template>
    </div>
  </fragment>
</template>
<script>
import * as action_types from "@/store/action-types";
import api from "@/api";
import Ref from "@/pages/LaboratoryResults/Ref";

export default {
  name: 'ResultsForm',
  components: {Ref},
  mounted() {
    this.$root.$on('laboratory:results:open-form', pk => this.loadForm(pk))
  },
  data() {
    return {
      loaded: false,
      confirmed: false,
      saved: false,
      allow_reset_confirm: false,
      pk: null,
      research: {},
      comment: '',
      result: [],
    };
  },
  methods: {
    async loadForm(pk) {
      if (pk === -1) {
        return;
      }
      this.loaded = false;
      await this.$store.dispatch(action_types.INC_LOADING);
      const {data} = await api('laboratory/form', {pk});
      this.pk = data.pk;
      this.research = data.research;
      this.comment = data.comment;
      this.result = data.result;
      this.confirmed = data.confirmed;
      this.saved = data.saved;
      this.allow_reset_confirm = data.allow_reset_confirm;
      this.loaded = true;
      $(this.$refs.root).scrollTop(0);
      if (!data.confirmed) {
        setTimeout(() => {
          const $rf = $('.result-field');
          if ($rf.length) {
            const idx = data.result.findIndex(r => !Boolean(r.value));
            if (idx !== -1) {
              $rf.eq(idx).focus();
            }
          }
        }, 0);
      }
      await this.$store.dispatch(action_types.DEC_LOADING);
    },
    async clearAll() {
      try {
        await this.$dialog.confirm('Вы действительно очистить все значения?')
      } catch (_) {
        return
      }
      for (const i of this.result) {
        i.value = '';
      }
    },
    async save(withoutReloading = false) {
      await this.$store.dispatch(action_types.INC_LOADING);
      const {ok, message} = await api('laboratory/save', this, ['pk', 'result', 'comment']);
      if (!ok) {
        errmessage(message);
      } else {
        okmessage('Сохранено');
      }
      if (!withoutReloading) {
        this.$root.$emit('laboratory:reload-direction:with-open-first');
      }
      await this.$store.dispatch(action_types.DEC_LOADING);
      return ok;
    },
    async confirm() {
      await this.$store.dispatch(action_types.INC_LOADING);
      const {ok, message} = await api('laboratory/confirm', this, 'pk');
      if (!ok) {
        errmessage(message);
      } else {
        okmessage('Подтверждено');
      }
      this.$root.$emit('laboratory:reload-direction:with-open-first');
      await this.$store.dispatch(action_types.DEC_LOADING);
      return ok;
    },
    async saveAndConfirm() {
      const saveResult = await this.save(true);
      if (!saveResult) {
        return;
      }

      await this.confirm();
    },
    moveFocusNext(e) {
      const $rf = $('.result-field');
      const index = $rf.index(e.target) + 1;
      if ($rf.eq(index).length) {
        $rf.eq(index).focus();
      } else {
        this.save();
      }
    }
  },
}
</script>

<style scoped lang="scss">
.root {
  position: absolute;
  top: 0 !important;
  right: 0;
  left: 0;
  bottom: 34px !important;
  overflow-x: visible;
  overflow-y: auto;
}

.val {
  position: relative;
}

.val .unit {
  color: #888;
  top: 1px;
  right: 2px;
  display: block;
}

.val .unit:not(:empty) {
  z-index: 1;
  word-break: keep-all;
  white-space: nowrap;
  height: 20px;
  margin-top: -24px;
  padding-bottom: 4px;
  padding-right: 5px;
  float: right;
  text-align: right;
  box-sizing: border-box;
  overflow: hidden;
  font-size: 12px;
  max-width: 64px;
}

.val input.with-units {
  padding-right: calc(64px / 9 * var(--x) + 7px);
  top: 0;
  left: 0;
  display: block;
}

[data-x="1"] {
  --x: 1;
}

[data-x="2"] {
  --x: 2;
}

[data-x="3"] {
  --x: 3;
}

[data-x="4"] {
  --x: 4;
}

[data-x="5"] {
  --x: 5;
}

[data-x="6"] {
  --x: 6;
}

[data-x="7"] {
  --x: 7;
}

[data-x="8"] {
  --x: 8;
}

[data-x="9"] {
  --x: 9;
}

.fraction-title {
  font-weight: normal;
  font-size: 14px;
  display: block;
  min-height: 100%;
  height: 100%;
  margin: 0;
  cursor: pointer !important;
}

.header-button {
  width: 100%;
}

.table-header th {
  padding: 2px 2px 2px 8px;
  position: sticky;
  top: -1px;
  background-color: white;
  z-index: 2;
  box-shadow: 2px 0 2px rgba(0, 0, 0, .1);
}

.isnorm_maybe {
  border-color: darkgoldenrod;
  box-shadow: 0 0 4px darkgoldenrod;
}

.isnorm_not_normal {
  border-color: darkred;
  box-shadow: 0 0 4px darkred;
}
</style>