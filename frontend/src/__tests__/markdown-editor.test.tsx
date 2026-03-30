/**
 * MarkdownEditor 组件测试
 *
 * 测试覆盖：
 * 1. 默认渲染编辑区和预览区（分栏模式）
 * 2. 工具栏按钮存在
 * 3. 输入文本触发 onChange
 * 4. 视图模式切换
 * 5. 字数统计显示
 */
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import MarkdownEditor from "@/components/business/markdown-editor";

// Mock react-markdown（避免 ESM 兼容问题）
vi.mock("react-markdown", () => ({
  default: ({ children }: { children: string }) => <div data-testid="preview">{children}</div>,
}));

vi.mock("remark-gfm", () => ({
  default: () => {},
}));

describe("MarkdownEditor", () => {
  const defaultProps = {
    value: "",
    onChange: vi.fn(),
  };

  it("渲染编辑区", () => {
    render(<MarkdownEditor {...defaultProps} />);
    const textarea = screen.getByRole("textbox");
    expect(textarea).toBeDefined();
  });

  it("显示 placeholder", () => {
    render(<MarkdownEditor {...defaultProps} placeholder="请输入内容" />);
    const textarea = screen.getByPlaceholderText("请输入内容");
    expect(textarea).toBeDefined();
  });

  it("输入触发 onChange", async () => {
    const onChange = vi.fn();
    render(<MarkdownEditor value="" onChange={onChange} />);
    const textarea = screen.getByRole("textbox");
    await userEvent.type(textarea, "测试");
    expect(onChange).toHaveBeenCalled();
  });

  it("显示字数统计", () => {
    render(<MarkdownEditor value="测试文本共六个字" onChange={vi.fn()} />);
    // 字数统计应显示 "8 字"
    expect(screen.getByText(/\d+ 字/)).toBeDefined();
  });

  it("预览区渲染 Markdown 内容", () => {
    render(<MarkdownEditor value="# 标题" onChange={vi.fn()} />);
    const preview = screen.getByTestId("preview");
    expect(preview.textContent).toContain("# 标题");
  });

  it("全屏按钮存在", () => {
    render(<MarkdownEditor {...defaultProps} />);
    const fullscreenBtn = screen.getByTitle("全屏编辑");
    expect(fullscreenBtn).toBeDefined();
  });

  it("工具栏包含加粗按钮", () => {
    render(<MarkdownEditor {...defaultProps} />);
    const boldBtn = screen.getByTitle("加粗");
    expect(boldBtn).toBeDefined();
  });

  it("工具栏包含插入表格按钮", () => {
    render(<MarkdownEditor {...defaultProps} />);
    const tableBtn = screen.getByTitle("插入表格");
    expect(tableBtn).toBeDefined();
  });

  it("视图模式切换按钮存在", () => {
    render(<MarkdownEditor {...defaultProps} />);
    expect(screen.getByTitle("编辑模式")).toBeDefined();
    expect(screen.getByTitle("分栏模式")).toBeDefined();
    expect(screen.getByTitle("预览模式")).toBeDefined();
  });

  it("选中文本时触发 onSelectionChange", () => {
    const onSelectionChange = vi.fn();
    render(
      <MarkdownEditor
        value="Hello World"
        onChange={vi.fn()}
        onSelectionChange={onSelectionChange}
      />
    );
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    // 模拟选中
    textarea.setSelectionRange(0, 5);
    fireEvent.mouseUp(textarea);
    expect(onSelectionChange).toHaveBeenCalled();
  });
});
