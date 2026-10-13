.PHONY: help test lint check fmt install help
# 常用入口。改完键位/补丁后，最快能跑的就是 test 和 check。

help:
	@echo "make test     - 单元测试（unittest）"
	@echo "make lint     - ruff 检查"
	@echo "make fmt      - ruff 格式化（原地）"
	@echo "make check    - lint + format + 脚本语法，提交前跑这个"
	@echo "make install  - 安装到本机（等价 ./install.sh）"

# --- Python -------------------------------------------------------------
PYFILES := $(wildcard system/patch/*.py tests/*.py tools/*.py)

test:
	python3 -m unittest tests.test_mimo_asr

lint:
	ruff check .

fmt:
	ruff format $(PYFILES)

# --- 脚本语法（按 shebang 分流） ----------------------------------------
SHELL_SCRIPTS := install.sh $(wildcard scripts/*)

check: lint
	ruff format --check $(PYFILES)
	@for f in $(SHELL_SCRIPTS); do \
	  [ -f "$$f" ] || continue; \
	  case "$$(head -1 $$f)" in \
	    *bash*|*/sh) bash -n $$f ;; \
	    *python*) python3 -m py_compile $$f ;; \
	  esac \
	done

install:
	bash ./install.sh
